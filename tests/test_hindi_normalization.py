import json
from unittest.mock import AsyncMock

import httpx
import pytest

from packages.shared.settings import Settings
from packages.voice.pipeline import Pipeline, valid_hindi_normalization


@pytest.mark.parametrize("raw,normalized", [
    ("میرے رپورٹ کے بارے میں بتائیے", "मेरी रिपोर्ट के बारे में बताइए"),
    ("mera WBC 7500 hai", "मेरा WBC 7500 है"),
    ("मेरा WBC 7500 है", "मेरा WBC 7500 है"),
])
async def test_hindi_normalizes_inside_existing_routing_call(raw, normalized):
    events = []
    async def publish(event):
        events.append(event)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": "Please review your report."}}]}
    ))) as client:
        pipeline = Pipeline(Settings(_env_file=None, groq_api_key="test"), client)
        async def model(instruction, payload, structured=False, review=False):
            if structured:
                assert "Urdu script" in instruction
                return json.dumps({"language": "hi", "english_query": "Explain my report",
                                   "normalized_query": normalized, "scope": "medical"})
            if review:
                return '{"approved": true}'
            return "कृपया अपनी रिपोर्ट देखें।"
        pipeline.gemini = AsyncMock(side_effect=model)
        result = await pipeline.answer(raw, {}, on_stage=publish)
        assert result["language"] == "hi"
        transcript_events = [event for event in events if event.get("type") == "user_transcript"]
        assert transcript_events[0]["text"] == raw
        assert transcript_events[1]["text"] == normalized
        assert transcript_events[1]["normalized"] is True
        assert sum(call.kwargs.get("structured", False) or
                   (len(call.args) > 2 and call.args[2] is True)
                   for call in pipeline.gemini.call_args_list) == 1


@pytest.mark.parametrize("language,normalized,raw", [
    ("unsupported", "", "مرحبا"),
    ("unknown", "", "میرے رپورٹ"),
    ("hi", "", "میرے رپورٹ"),
    ("hi", "मेरा WBC 999 है", "میرا WBC 7500 ہے"),
    ("hi", "میرا رپورٹ", "میرا رپورٹ"),
])
async def test_rejected_or_invalid_normalization_does_not_reach_medical_model(language, normalized, raw):
    events = []
    async def publish(event):
        events.append(event)
    def no_medical(request):
        pytest.fail("Rejected input must not reach the answer model")
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_medical)) as client:
        pipeline = Pipeline(Settings(_env_file=None, groq_api_key="test"), client)
        pipeline.gemini = AsyncMock(return_value=json.dumps({
            "language": language, "normalized_query": normalized,
            "english_query": "Explain", "scope": "medical",
        }))
        result = await pipeline.answer(raw, {}, on_stage=publish)
        assert result["input_rejected"] is True
        assert not any(event.get("normalized") for event in events)


async def test_patient_name_is_never_normalized():
    events = []
    async def publish(event):
        events.append(event)
    async with httpx.AsyncClient() as client:
        pipeline = Pipeline(Settings(_env_file=None, groq_api_key="test"), client)
        pipeline.care_state["stage"] = "patient"
        pipeline.gemini = AsyncMock(return_value=json.dumps({
            "language": "hi", "normalized_query": "हरी शंकर प्रसाद",
            "english_query": "Appointment name", "scope": "unclear",
        }))
        await pipeline.answer("Hari Sankar Prasad", {}, on_stage=publish)
        assert [e["text"] for e in events if e.get("type") == "user_transcript"] == [
            "Hari Sankar Prasad",
        ]


async def test_urdu_script_hindi_retries_with_explicit_normalization_instruction():
    events = []

    async def publish(event):
        events.append(event)

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": "Safe answer."}}]}
    ))) as client:
        pipeline = Pipeline(Settings(_env_file=None, groq_api_key="test"), client)
        responses = iter([
            {"language": "unsupported", "english_query": "Unsupported input", "scope": "medical"},
            {"language": "hi", "english_query": "Explain my report", "normalized_query": "मेरी रिपोर्ट के बारे में बताइए", "scope": "medical", "report_related": True},
        ])

        async def model(instruction, payload, structured=False, review=False):
            if structured:
                return json.dumps(next(responses))
            if review:
                return '{"approved": true}'
            return "सुरक्षित उत्तर।"

        pipeline.gemini = AsyncMock(side_effect=model)
        result = await pipeline.answer("میرے ریپورٹ کے بارے میں بتائیے", {}, on_stage=publish)
        assert result["language"] == "hi"
        assert any(event.get("stage") == "normalize_hindustani" for event in events)
        assert any(event.get("normalized") and "देवनागरी" not in event["text"] for event in events)


def test_numeric_guard_preserves_values_and_rejects_new_values():
    assert valid_hindi_normalization("Hb 9.2 g/dL hai", "Hb 9.2 g/dL है")
    assert not valid_hindi_normalization("Hb 9.2 g/dL hai", "Hb 12 g/dL है")
    assert not valid_hindi_normalization("report samjhao", "रिपोर्ट में 9.2 है")
