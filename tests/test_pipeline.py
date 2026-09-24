import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from packages.shared.settings import Settings
from packages.voice.pipeline import Pipeline, PipelineError


def config():
    return Settings(
        _env_file=None, language_provider="gemini", gemini_api_key=SecretStr("test"), groq_api_key=SecretStr("test")
    )


def gemini_reply(text):
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "language" in data:
            data.setdefault("scope", "doctor_connect" if data.get("care_action", "none") != "none" else "medical")
            text = json.dumps(data)
    except ValueError:
        pass
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


@pytest.fixture(autouse=True)
def approve_safety_for_legacy_pipeline_tests(monkeypatch):
    original = Pipeline.gemini
    async def gemini(self, instruction, payload, structured=False, review=False):
        if review:
            return '{"approved": true}'
        return await original(self, instruction, payload, structured)
    monkeypatch.setattr(Pipeline, "gemini", gemini)


@pytest.mark.parametrize("report_related,expected", [(True, "medical"), (False, "answer")])
async def test_progress_only_checks_report_when_needed(report_related, expected):
    events = []

    async def on_stage(event):
        events.append(event)

    def handler(request):
        if request.url.host == "api.groq.com":
            return httpx.Response(200, json={"choices": [{"message": {"content": "Answer"}}]})
        return gemini_reply(json.dumps({"language": "en", "english_query": "Question",
                                        "report_related": report_related}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await Pipeline(config(), client).answer("Question", {}, on_stage=on_stage)
    assert [event["stage"] for event in events if event["status"] == "working"] == [
        "translate_in", expected, "safety_check",
    ]


@pytest.mark.parametrize("native", ["hi", "te"])
async def test_native_language_persists_until_explicit_switch(native):
    turns = iter([(native, False), ("en", False), ("en", False), ("en", True)])
    preferences = []

    def handler(request):
        body = json.loads(request.content)
        if request.url.host == "api.groq.com":
            return httpx.Response(200, json={"choices": [{"message": {"content": "Answer"}}]})
        payload = json.loads(body["contents"][0]["parts"][0]["text"])
        if "query" in payload:
            preferences.append(payload["preferred_response_language"])
            language, switch = next(turns)
            assert "Hindi mixed with English" in body["systemInstruction"]["parts"][0]["text"]
            return gemini_reply(json.dumps({"language": language,
                                           "explicit_language_switch": switch,
                                           "english_query": "Explain hemoglobin"}))
        assert payload["target_language"] == native
        return gemini_reply("Native answer")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        for query, expected in [("मेरी रिपोर्ट समझाइए", native), ("hemoglobin level?", native),
                                ("okay thanks", native), ("Please speak in English", "en")]:
            assert (await pipeline.answer(query, {}))["language"] == expected
        assert preferences == [None, native, native, native]
        assert Pipeline(config(), client).response_language is None


@pytest.mark.parametrize("language", ["hi", "te", "en"])
async def test_pipeline_preserves_report_and_routes_language(language):
    requests = []
    report = {"findings": [{"value": 9.2, "unit": "g/dL"}]}

    def handler(request):
        body = json.loads(request.content)
        requests.append((request.url.host, body))
        if request.url.host == "api.groq.com":
            assert request.url.path == "/openai/v1/chat/completions"
            assert request.headers["authorization"] == "Bearer test"
            assert body["model"] == "openai/gpt-oss-120b"
            assert body["reasoning_effort"] == "low"
            assert body["include_reasoning"] is False
            assert body["max_completion_tokens"] == 1024
            assert "max_tokens" not in body
            assert "reasoning_format" not in body
            payload = json.loads(body["messages"][-1]["content"])
            assert payload["report_context"] == report
            assert payload["english_query"] == "Explain my result"
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "English answer"}}]}
            )
        if len(requests) == 1:
            assert request.url.path.endswith('/gemini-3.5-flash-lite:generateContent')
            assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
            assert "temperature" not in body["generationConfig"]
            return gemini_reply(
                json.dumps({"language": language, "english_query": "Explain my result"})
            )
        assert json.loads(body["contents"][0]["parts"][0]["text"])["target_language"] == language
        return gemini_reply("Translated answer")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Pipeline(config(), client).answer("Native question", report)
    assert result["language"] == language
    assert len(requests) == (2 if language == "en" else 3)
    assert result["text"] == ("English answer" if language == "en" else "Translated answer")
    assert "pipeline_total" in result["timings_ms"]


async def test_provider_error_does_not_expose_body():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text="SECRET PROVIDER DATA"))
    ) as client:
        with pytest.raises(PipelineError, match="HTTP 401") as caught:
            await Pipeline(config(), client).answer("Question", {})
        assert "SECRET" not in str(caught.value)


async def test_malformed_translation_never_calls_medical():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: gemini_reply("not json"))
    ) as client:
        with pytest.raises(PipelineError, match="Translation format"):
            await Pipeline(config(), client).answer("Question", {})


async def test_gemini_404_is_actionable_and_does_not_leak_body():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404, text="SECRET DATA"))
    ) as client:
        with pytest.raises(PipelineError, match="GEMINI_MODEL") as caught:
            await Pipeline(config(), client).answer("Question", {})
        assert "SECRET" not in str(caught.value)


async def test_cancellation_stops_provider_chain():
    entered = asyncio.Event()
    calls = []

    async def handler(request):
        calls.append(request.url.host)
        entered.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        task = asyncio.create_task(Pipeline(config(), client).answer("Question", {}))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert calls == ["generativelanguage.googleapis.com"]


@pytest.mark.parametrize("payload", [None, {"candidates": [None]}, {"candidates": [{"content": {"parts": [None]}}]}])
async def test_malformed_gemini_shapes_are_safe(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=json.dumps(payload)))
    ) as client:
        with pytest.raises(PipelineError, match="no usable response"):
            await Pipeline(config(), client).answer("Question", {})


async def test_provider_timeout_is_safe():
    def handler(request):
        raise httpx.ReadTimeout("private upstream diagnostic", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PipelineError, match="took too long"):
            await Pipeline(config(), client).answer("Question", {})


@pytest.mark.parametrize("status, message", [(400, "model permissions"), (403, "model permissions"), (404, "model permissions"), (429, "usage limit")])
async def test_groq_access_errors_are_actionable(status, message):
    def handler(request):
        if request.url.host == "api.groq.com":
            return httpx.Response(status, text="PRIVATE PROVIDER DATA")
        return gemini_reply(json.dumps({"language": "en", "english_query": "Question"}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PipelineError, match=message) as caught:
            await Pipeline(config(), client).answer("Question", {})
    assert "PRIVATE" not in str(caught.value)


async def test_cancel_during_stage_notification_never_starts_provider():
    calls = []

    async def on_stage(event):
        raise asyncio.CancelledError()

    def handler(request):
        calls.append(request)
        return gemini_reply("unused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(asyncio.CancelledError):
            await Pipeline(config(), client).answer("Question", {}, on_stage=on_stage)
    assert calls == []


@pytest.mark.parametrize("finish_reason", ["stop", "length"])
async def test_only_complete_final_answer_is_forwarded(finish_reason):
    def handler(request):
        if request.url.host == "api.groq.com":
            return httpx.Response(200, json={"choices": [{
                "finish_reason": finish_reason,
                "message": {"content": "Final explanation.", "reasoning": "DO NOT SPEAK THIS"},
            }]})
        return gemini_reply(json.dumps({"language": "en", "english_query": "Question"}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pipeline = Pipeline(config(), client)
        if finish_reason == "length":
            with pytest.raises(PipelineError, match="cut short"):
                await pipeline.answer("Question", {})
        else:
            result = await pipeline.answer("Question", {})
            assert result["text"] == "Final explanation."
            assert "DO NOT SPEAK" not in json.dumps(result)
