import json

import httpx
import pytest

from packages.shared.settings import Settings
from packages.voice.pipeline import Pipeline, PipelineError


@pytest.mark.parametrize("status", [429, 500, 503])
@pytest.mark.parametrize("mode", ["text", "routing", "review"])
async def test_transient_failure_falls_back_with_same_prompt(status, mode):
    seen = []
    output = {"text": "Hello", "review": '{"approved": false}', "routing": json.dumps({
        "language": "en", "english_query": "Explain report", "scope": "medical",
        "explicit_language_switch": False, "care_action": "none", "care_value": "",
        "report_related": True,
    })}[mode]

    def handler(request):
        seen.append(request.url.host)
        if request.url.host != "api.groq.com":
            return httpx.Response(status)
        body = json.loads(request.content)
        assert body["messages"][0]["content"] == "Keep safety rules"
        assert body["model"] == "openai/gpt-oss-120b"
        if mode != "text":
            assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                                                     "message": {"content": output}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Pipeline(Settings(_env_file=None, language_provider="gemini"), client).gemini(
            "Keep safety rules", {}, structured=mode == "routing", review=mode == "review")
    assert result == output
    assert seen == ["generativelanguage.googleapis.com", "api.groq.com"]


@pytest.mark.parametrize("status,enabled", [(401, True), (404, True), (503, False)])
async def test_no_fallback_for_config_error_or_disabled(status, enabled):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PipelineError):
            await Pipeline(Settings(_env_file=None, language_provider="gemini", gemini_groq_fallback=enabled), client).gemini("Test", {})
    assert seen == ["generativelanguage.googleapis.com"]


@pytest.mark.parametrize("content", ['{"approved":"true"}', 'not json', ''])
async def test_invalid_review_fails_closed(content):
    def handler(request):
        if request.url.host != "api.groq.com":
            return httpx.Response(503)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                                                     "message": {"content": content}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PipelineError):
            await Pipeline(Settings(_env_file=None), client).gemini("Review", {}, review=True)
