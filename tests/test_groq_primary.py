import json

import httpx
import pytest

from packages.shared.settings import Settings
from packages.voice.pipeline import Pipeline


@pytest.mark.parametrize("language", ["en", "hi"])
@pytest.mark.parametrize("approved", [True, False])
async def test_groq_only_answer_preserves_review_and_translation(language, approved):
    calls = []

    def handler(request):
        assert request.url.host == "api.groq.com"
        body = json.loads(request.content)
        schema = body.get("response_format", {}).get("json_schema", {}).get("name")
        if schema == "routing":
            content = json.dumps({"language": language, "english_query": "Explain report",
                                  "scope": "medical", "care_action": "none", "care_value": "",
                                  "explicit_language_switch": False, "report_related": True})
        elif schema == "safety_review":
            content = json.dumps({"approved": approved})
        else:
            content = "Sample explanation"
        calls.append(schema or "text")
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                                                     "message": {"content": content}}]})

    config = Settings(_env_file=None, groq_api_key="test")
    assert config.language_provider == "groq"
    assert config.missing(False) == []
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await Pipeline(config, client).answer("Explain my report", {"findings": []})
    assert calls == ["routing", "text"] + (["text"] if language != "en" else []) + ["safety_review"]
    assert result["language"] == language
    if approved:
        assert result["text"] == "Sample explanation"
    else:
        assert result["guardrail"] == "unsafe"
