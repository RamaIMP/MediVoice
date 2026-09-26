import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from livekit.agents import llm

from packages.shared.settings import Settings
from packages.voice.agent import MedicalLLM, prepare_report, trace_conversation_item
from packages.voice.pipeline import PipelineError


def test_bvc_enabled_only_for_room_audio(monkeypatch):
    from packages.voice.agent import voice_room_options
    sentinel = object()
    calls = []
    monkeypatch.setattr("packages.voice.agent.noise_cancellation.BVC",
                        lambda: calls.append(True) or sentinel)
    config = Settings(_env_file=None)
    assert voice_room_options(config, console=True) == {}
    assert calls == []
    options = voice_room_options(config, console=False)
    assert options["room_options"].audio_input.noise_cancellation is sentinel
    assert calls == [True]
    config.background_voice_cancellation = False
    assert voice_room_options(config, console=False) == {}
    assert calls == [True]


def test_audio_thresholds_are_conservative_and_configurable():
    config = Settings(_env_file=None)
    assert config.vad_activation_threshold == 0.65
    assert config.vad_min_speech_duration == 0.12
    assert config.interruption_min_duration == 0.65
    assert config.max_call_duration_seconds == 180
    assert config.idle_call_timeout_seconds == 60
    assert Settings(_env_file=None, vad_min_speech_duration=0.08).vad_min_speech_duration == 0.08


def test_conversation_handoff_does_not_access_message_fields(monkeypatch):
    events = []
    monkeypatch.setattr("packages.voice.agent.trace", lambda name, **data: events.append((name, data)))
    trace_conversation_item(SimpleNamespace(item=llm.AgentHandoff(new_agent_id="test-agent")))
    assert events == [("conversation_event", {"item_type": "agent_handoff"})]


def test_conversation_message_retains_debug_fields(monkeypatch):
    events = []
    monkeypatch.setattr("packages.voice.agent.trace", lambda name, **data: events.append((name, data)))
    trace_conversation_item(SimpleNamespace(item=llm.ChatMessage(role="user", content=["Hello"])))
    assert events == [("conversation_item", {"role": "user", "text": "Hello", "interrupted": False})]


async def test_pipeline_error_logged_without_private_debug_mode(caplog):
    events = []

    async def publish(event):
        events.append(event)

    class FailedPipeline:
        settings = SimpleNamespace(groq_model="test", language_provider="groq")

        async def answer(self, *args, **kwargs):
            raise PipelineError("Gemini request failed (HTTP 404).")

    model = MedicalLLM(FailedPipeline(), {}, publish)
    context = llm.ChatContext()
    context.add_message(role="user", content="Explain my report")
    async with model.chat(chat_ctx=context) as stream:
        chunks = [chunk async for chunk in stream]
    assert "Answer pipeline failed" in caplog.text
    assert "Gemini request failed (HTTP 404)." in caplog.text
    assert "Explain my report" not in caplog.text
    assert events == [{"type": "error", "message": "Gemini request failed (HTTP 404)."}]
    assert "could not complete" in chunks[0].delta.content
    await model.aclose()


def console_settings(tmp_path):
    return Settings(_env_file=None, database_path=tmp_path / "unused.db",
                    gemini_api_key="test", groq_api_key="test",
                    assemblyai_api_key="test", elevenlabs_api_key="test",
                    livekit_url="", livekit_api_key="", livekit_api_secret="")


async def test_console_loads_sample_without_livekit_or_database(tmp_path):
    config = console_settings(tmp_path)
    ctx = SimpleNamespace(is_fake_job=lambda: True, connect=AsyncMock())
    report = await prepare_report(ctx, config)
    assert isinstance(report, dict) and report
    ctx.connect.assert_not_awaited()
    assert not config.database_path.exists()


async def test_browser_mode_still_requires_livekit_credentials(tmp_path):
    ctx = SimpleNamespace(is_fake_job=lambda: False, connect=AsyncMock())
    with pytest.raises(RuntimeError, match="LIVEKIT"):
        await prepare_report(ctx, console_settings(tmp_path))
    ctx.connect.assert_not_awaited()


def test_console_still_requires_direct_voice_provider_keys(tmp_path):
    config = console_settings(tmp_path)
    config.assemblyai_api_key = type(config.assemblyai_api_key)("")
    assert config.missing(console=True) == ["ASSEMBLYAI_API_KEY"]


async def test_agent_emits_pipeline_answer_and_filters_system_messages():
    events = []

    async def publish(event):
        events.append(event)

    class FakePipeline:
        settings = SimpleNamespace(groq_model="test", language_provider="groq")

        async def answer(self, query, report, history, on_stage):
            assert query == "Explain hemoglobin"
            assert report == {"sample": True}
            assert history == [{"role": "assistant", "text": "Welcome"}]
            await on_stage({"type": "user_transcript", "text": "मेरी रिपोर्ट", "normalized": True})
            await on_stage({"stage": "medical", "status": "complete", "ms": 1})
            return {"text": "Sample answer", "language": "en", "timings_ms": {"medical": 1}}

    model = MedicalLLM(FakePipeline(), {"sample": True}, publish)
    context = llm.ChatContext()
    context.add_message(role="system", content="Do not forward as patient history")
    context.add_message(role="assistant", content="Welcome")
    context.add_message(role="user", content="Explain hemoglobin")
    async with model.chat(chat_ctx=context) as stream:
        chunks = [chunk async for chunk in stream]
    assert chunks[0].delta.content == "Sample answer"
    assert events[-1]["type"] == "answer_ready"
    assert events[0]["type"] == "user_transcript"
    assert events[0]["id"] == context.items[-1].id
    assert events[0]["text"] == "मेरी रिपोर्ट"
    await model.aclose()


async def test_agent_cancellation_does_not_emit_answer():
    entered = asyncio.Event()
    events = []

    async def publish(event):
        events.append(event)

    class SlowPipeline:
        settings = SimpleNamespace(groq_model="test", language_provider="groq")

        async def answer(self, *args, **kwargs):
            entered.set()
            await asyncio.Event().wait()

    model = MedicalLLM(SlowPipeline(), {}, publish)
    context = llm.ChatContext()
    context.add_message(role="user", content="Question")
    stream = model.chat(chat_ctx=context)
    await entered.wait()
    await stream.aclose()
    assert events == []
    await model.aclose()


async def test_agent_publishes_doctor_panel_before_spoken_answer():
    events = []

    async def publish(event):
        events.append(event)

    class CarePipeline:
        settings = SimpleNamespace(groq_model="test", language_provider="groq")

        async def answer(self, *args, **kwargs):
            return {"text": "Choose a demo doctor.", "language": "en", "timings_ms": {},
                    "care_state": {"stage": "search", "revision": 1}}

    model = MedicalLLM(CarePipeline(), {}, publish)
    context = llm.ChatContext()
    context.add_message(role="user", content="Find me a doctor")
    async with model.chat(chat_ctx=context) as stream:
        chunks = [chunk async for chunk in stream]
    assert events[0]["type"] == "doctor_connect"
    assert chunks[0].delta.content == "Choose a demo doctor."
    await model.aclose()
