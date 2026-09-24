from unittest.mock import patch

import pytest
from pydantic import ValidationError

from packages.shared.settings import Settings
from packages.voice.agent import build_tts


def config(**kwargs):
    values = dict(
        tts_provider="cartesia_livekit", livekit_url="wss://test.livekit.cloud",
        livekit_api_key="test-key", livekit_api_secret="test-secret",
        assemblyai_api_key="test", gemini_api_key="test", groq_api_key="test",
        elevenlabs_api_key="",
    )
    values.update(kwargs)
    return Settings(_env_file=None, **values)


def test_cartesia_uses_livekit_auth_and_native_streaming():
    settings = config()
    with patch("packages.voice.agent.inference.TTS") as cartesia, \
            patch("packages.voice.agent.elevenlabs.TTS") as elevenlabs:
        provider, voice = build_tts(settings)
    assert provider is voice is cartesia.return_value
    cartesia.assert_called_once_with(
        model="cartesia/sonic-3.6", voice=settings.cartesia_voice_id,
        api_key="test-key", api_secret="test-secret",
    )
    elevenlabs.assert_not_called()


async def test_cartesia_sdk_resolves_inference_gateway_not_room_url(monkeypatch):
    monkeypatch.delenv("LIVEKIT_INFERENCE_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    settings = config()
    provider, voice = build_tts(settings)
    try:
        assert provider is voice
        assert provider._opts.base_url == "https://agent-gateway.livekit.cloud/v1"
        assert provider._opts.base_url != settings.livekit_url
    finally:
        await provider.aclose()


def test_elevenlabs_remains_selectable():
    with patch("packages.voice.agent.elevenlabs.TTS") as elevenlabs, \
            patch("packages.voice.agent.tts.StreamAdapter") as adapter, \
            patch("packages.voice.agent.inference.TTS") as cartesia:
        provider, voice = build_tts(config(tts_provider="elevenlabs", elevenlabs_api_key="test"))
    assert provider is elevenlabs.return_value
    assert voice is adapter.return_value
    adapter.assert_called_once_with(tts=provider)
    assert elevenlabs.call_args.kwargs["model"] == "eleven_v3"
    cartesia.assert_not_called()


@pytest.mark.parametrize("console", [True, False])
def test_cartesia_requires_livekit_but_not_elevenlabs(console):
    assert config().missing(console=console) == []
    assert config(livekit_api_secret="").missing(console=console) == ["LIVEKIT_API_SECRET"]


def test_unknown_provider_rejected():
    with pytest.raises(ValidationError):
        config(tts_provider="typo")


@pytest.mark.parametrize("model", ["cartesia/sonic-3.6", "sonic-3.6"])
def test_direct_cartesia_uses_own_key_not_inference(model):
    settings = config(tts_provider="cartesia_direct", cartesia_api_key="direct-test-key",
                      cartesia_model=model)
    with patch("packages.voice.agent.cartesia.TTS") as direct, \
            patch("packages.voice.agent.inference.TTS") as gateway:
        provider, voice = build_tts(settings)
    assert provider is voice is direct.return_value
    direct.assert_called_once_with(model="sonic-3.6", voice=settings.cartesia_voice_id,
                                   api_key="direct-test-key")
    gateway.assert_not_called()


def test_direct_cartesia_requires_own_key():
    settings = config(tts_provider="cartesia_direct", cartesia_api_key="")
    assert settings.missing(console=True) == ["CARTESIA_API_KEY"]


async def test_direct_cartesia_endpoint_and_language_switching():
    settings = config(tts_provider="cartesia_direct", cartesia_api_key="test")
    provider, voice = build_tts(settings)
    try:
        assert provider is voice
        assert provider._opts.base_url == "https://api.cartesia.ai"
        assert provider._opts.model == "sonic-3.6"
        for language in ("en", "hi", "te"):
            voice.update_options(language=language)
            assert voice._opts.language == language
    finally:
        await provider.aclose()


def test_direct_cartesia_console_does_not_require_livekit_but_ui_does():
    settings = config(tts_provider="cartesia_direct", cartesia_api_key="test",
                      livekit_url="", livekit_api_key="", livekit_api_secret="")
    assert settings.missing(console=True) == []
    assert settings.missing(console=False) == [
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    ]
