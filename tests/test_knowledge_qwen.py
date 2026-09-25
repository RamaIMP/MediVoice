import json

import httpx
import pytest

from packages.knowledge.qwen_pdf_to_json import (
    compile_document,
    extract_page,
    medical_document,
    validate_page,
)


def content(number=1):
    return {"page_number": number, "is_medical_report": True, "metadata": {
                "patient_name": "Sample", "age": "35", "sex": "Female",
                "lab_name": "Sample Lab", "lab_address": None, "doctors": []},
            "notes": [], "tables": [{"title": None,
            "columns": ["Test", "Value", "Unit"],
            "rows": [["WBC", "7500", "cells/uL"]]}], "uncertainties": []}


def test_two_pages_compile_without_merging_values():
    pages = [{"page_number": n, "status": "extracted", "content": content(n)}
             for n in (1, 2)]
    result = compile_document("sample.pdf", 8, 2, pages)
    assert result["extraction_status"] == "complete"
    assert result["scope"] == "selected_pages"
    assert result["source_page_count"] == 8
    assert result["pages"] == pages


def test_partial_and_duplicate_pages():
    failed = [{"page_number": 1, "status": "failed"}]
    assert compile_document("sample.pdf", 2, 2, failed)["extraction_status"] == "partial"
    with pytest.raises(ValueError):
        compile_document("sample.pdf", 2, 2, failed * 2)


@pytest.mark.parametrize("change", ["number", "width", "extra", "empty"])
def test_validation(change):
    page = content()
    if change == "number":
        page["page_number"] = 2
    elif change == "width":
        page["tables"][0]["rows"][0].pop()
    elif change == "extra":
        page["bounding_box"] = []
    else:
        page["tables"] = []
    with pytest.raises(ValueError):
        validate_page(json.dumps(page), 1)


def test_semantic_column_roles_must_match_the_visible_table_width():
    page = content()
    page["tables"][0]["column_roles"] = ["test", "value"]
    with pytest.raises(ValueError, match="role width"):
        validate_page(json.dumps(page), 1)


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_one_image_per_request(finish):
    def respond(request):
        body = json.loads(request.content)
        images = [part for part in body["messages"][0]["content"]
                  if part["type"] == "image_url"]
        assert len(images) == 1
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"finish_reason": finish,
            "message": {"content": json.dumps(content())}}], "usage": {"total_tokens": 3000}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        if finish == "stop":
            page, usage = extract_page(client, "secret", b"image", 1, check_relevance=True)
            assert page == content()
            assert usage["total_tokens"] == 3000
        else:
            with pytest.raises(ValueError, match="Incomplete"):
                extract_page(client, "secret", b"image", 1)


def test_pdf_text_layer_is_sent_as_numeric_cross_check_evidence():
    def respond(request):
        prompt = json.loads(request.content)["messages"][0]["content"][0]["text"]
        assert "7,400" in prompt
        assert "never change 7,400 to 7.400" in prompt
        assert "never to invent or move a decimal point" in prompt
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps(content())}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        extract_page(client, "secret", b"image", 1, check_relevance=True,
                     native_text="Total Leucocyte Count 7,400 /cu.mm")


def test_429_retry_once(monkeypatch):
    delays = []
    events = []
    monkeypatch.setattr("packages.knowledge.qwen_pdf_to_json.wait", delays.append)
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(429, headers={"retry-after": "3"})
    )) as client:
        with pytest.raises(RuntimeError, match="429"):
            extract_page(client, "secret", b"image", 1, on_progress=events.append)
    assert delays == [3]
    assert [event["state"] for event in events] == [
        "rate_limited", "processing", "rate_limit_reached"]
    assert events[0]["retry_after_seconds"] == 3
    assert "network" not in events[0]["message"].lower()


def test_medical_only_and_metadata_once():
    pages = [{"status": "extracted", "content": content(n), "usage": {"tokens": 123}}
             for n in (1, 2)]
    result = medical_document(pages)
    assert set(result) == {"patient", "lab", "doctors", "pages"}
    assert result["patient"]["name"] == "Sample"
    assert all(set(p) == {"page_number", "tables", "notes", "uncertainties"}
               for p in result["pages"])
    assert "usage" not in json.dumps(result)


def test_metadata_conflict_cannot_be_silently_merged():
    pages = [{"status": "extracted", "content": content(n)} for n in (1, 2)]
    pages[1]["content"]["metadata"]["patient_name"] = "Different patient"
    with pytest.raises(ValueError, match="Conflicting"):
        medical_document(pages)


def test_non_medical_page_cannot_contain_report_data():
    page = content()
    page["is_medical_report"] = False
    with pytest.raises(ValueError, match="non-medical"):
        validate_page(json.dumps(page), 1)


def test_only_the_first_page_requires_a_relevance_decision():
    page = content(2)
    del page["is_medical_report"]
    assert validate_page(json.dumps(page), 2)["is_medical_report"] is True
    with pytest.raises(ValueError, match="relevance decision"):
        validate_page(json.dumps(page), 1, require_relevance=True)
