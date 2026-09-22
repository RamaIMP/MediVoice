import json

import pytest
from pydantic import ValidationError

from packages.shared.settings import Settings
from scripts.check_setup import readiness


def test_readiness_does_not_return_secret_values():
    config = Settings(_env_file=None, gemini_api_key="private-value")
    result = readiness(config)
    assert "private-value" not in json.dumps(result)
    assert result["voice_configured"] is False
    assert "GROQ_API_KEY" in result["missing_voice_settings"]
    assert result["credentials_verified"] is False


def test_demo_is_text_only():
    result = readiness(Settings(_env_file=None, demo_mode=True))
    assert result["text_configured"] is True
    assert result["voice_configured"] is False


@pytest.mark.parametrize("values", [{"request_timeout_seconds": 0}, {"session_ttl_seconds": -1}])
def test_invalid_operational_settings_fail_early(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
