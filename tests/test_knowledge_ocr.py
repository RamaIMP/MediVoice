import json

import httpx
import pytest

from packages.knowledge.ocr_to_json import parse_ocr, post, structure, validate_page


def fixture():
    detections = [{"id": 0, "text": "WBC"}, {"id": 1, "text": "7500"}]
    page = {
        "page_number": 1, "uncertainties": [], "tables": [],
        "key_values": [{"label": {"text": "WBC", "detection_ids": [0]},
                        "value": {"text": "7500", "detection_ids": [1]}}],
    }
    return page, detections


def test_valid_evidence():
    page, detections = fixture()
    assert validate_page(page, 1, detections) == page


@pytest.mark.parametrize("change", ["value", "id", "page", "extra", "missing"])
def test_reject_unsupported_output(change):
    page, detections = fixture()
    if change == "value":
        page["key_values"][0]["value"]["text"] = "7600"
    elif change == "id":
        page["key_values"][0]["value"]["detection_ids"] = [99]
    elif change == "page":
        page["page_number"] = 2
    elif change == "extra":
        page["diagnosis"] = "invented"
    else:
        del page["tables"]
    with pytest.raises(ValueError):
        validate_page(page, 1, detections)


def test_table_width():
    page, detections = fixture()
    cell = page["key_values"][0]["label"]
    page["tables"] = [{"title": None, "columns": [cell], "rows": [[cell, None]]}]
    with pytest.raises(ValueError, match="width"):
        validate_page(page, 1, detections)


def test_parse_ocr_removes_geometry():
    box = {"points": [{"x": 0.1, "y": 0.2}]}
    result = parse_ocr({"data": [{"index": 0, "text_detections": [{
        "text_prediction": {"text": "WBC", "confidence": 0.95}, "bounding_box": box,
    }]}]})
    assert result == [{"id": 0, "text": "WBC", "confidence": 0.95}]


def test_http_error_does_not_expose_body():
    transport = httpx.MockTransport(lambda request: httpx.Response(429, text="private data"))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(RuntimeError, match="HTTP 429") as error:
            post(client, "https://example.test", "secret", {})
        assert "private data" not in str(error.value)


def test_empty_ocr_requires_review():
    with pytest.raises(ValueError, match="No OCR text"):
        parse_ocr({"data": [{"index": 0, "text_detections": []}]})


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_formatter(finish):
    page, detections = fixture()

    def respond(request):
        body = json.loads(request.content)
        assert "ocr_detections" in body["messages"][1]["content"]
        evidence = json.loads(body["messages"][1]["content"])["ocr_detections"]
        assert all(set(item) == {"id", "text"} for item in evidence)
        return httpx.Response(200, json={"choices": [{
            "finish_reason": finish, "message": {"content": json.dumps(page)},
        }]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        if finish == "stop":
            assert structure(client, "secret", 1, detections) == page
        else:
            with pytest.raises(ValueError, match="incomplete"):
                structure(client, "secret", 1, detections)
