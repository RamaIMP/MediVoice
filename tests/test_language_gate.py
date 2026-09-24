import json

import httpx
import pytest

from packages.voice.pipeline import Pipeline, unsupported_script
from tests.test_pipeline import config, gemini_reply


@pytest.mark.parametrize("language", ["en", "hi", "te"])
@pytest.mark.parametrize("name", ["Hari Sankar Prasad", "హరి శంకర్ ప్రసాద్", "हरि शंकर प्रसाद"])
async def test_patient_names_are_not_language_classified(language, name):
    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        if body["generationConfig"].get("responseMimeType"):
            assert "Names are opaque data" in str(body)
            # Even a mistaken language label must not override a valid name extraction.
            return gemini_reply(json.dumps({"language": "unknown", "english_query": "Appointment name",
                "care_action": "set_patient", "care_value": name, "explicit_language_switch": True}))
        return gemini_reply("Name confirmation prompt")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        pipeline.response_language = language
        pipeline.care_state.update(stage="patient", selected="demo-1", date="tomorrow", time="10 am")
        result = await pipeline.answer(name, {})
        assert result["care_state"]["stage"] == "patient_confirm"
        assert result["care_state"]["patient"] == name
        assert result["language"] == language
        assert pipeline.response_language == language
        edited = await pipeline.care_command("edit_patient", "", pipeline.care_state["revision"])
        assert edited["care_state"]["stage"] == "patient"


async def test_name_step_does_not_accept_invented_names_or_route_medical():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: gemini_reply(json.dumps({
        "language": "unsupported", "english_query": "Appointment name",
        "care_action": "set_patient", "care_value": "Invented Name"})))) as client:
        pipeline = Pipeline(config(), client)
        pipeline.care_state.update(stage="patient", selected="demo-1")
        result = await pipeline.answer("what should I enter?", {})
        assert pipeline.care_state["stage"] == "patient"
        assert pipeline.care_state["patient"] == ""
        assert result["guardrail"] == "unclear"


@pytest.mark.parametrize("query", ["продолжение следует", "你好", "Find डॉक्टर врач"])
async def test_other_scripts_never_call_any_provider(query):
    def handler(request):
        pytest.fail("Rejected script must not reach a provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        pipeline.response_language = "hi"
        before = dict(pipeline.care_state)
        result = await pipeline.answer(query, {})
        assert result["input_rejected"]
        assert result["language"] == "hi"
        assert pipeline.response_language == "hi"
        assert pipeline.care_state == before


@pytest.mark.parametrize("language", ["unsupported", "unknown"])
async def test_classifier_rejection_prevents_tools_medical_and_language_switch(language):
    calls = []

    def handler(request):
        calls.append(request.url.host)
        assert request.url.host == "generativelanguage.googleapis.com"
        return gemini_reply(json.dumps({
            "language": language, "english_query": "Find a doctor",
            "care_action": "search", "explicit_language_switch": True,
        }))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        pipeline.response_language = "te"
        before = dict(pipeline.care_state)
        result = await pipeline.answer("Necesito un médico", {})
        assert result["input_rejected"]
        assert pipeline.response_language == "te"
        assert pipeline.care_state == before
    assert len(calls) == 1


@pytest.mark.parametrize("query", ["मेरी hemoglobin report", "నా report", "meri report samjhao", "naa report cheppandi", "yes", "2", "English please"])
def test_allowed_scripts_and_code_switching_pass_initial_gate(query):
    assert not unsupported_script(query)
