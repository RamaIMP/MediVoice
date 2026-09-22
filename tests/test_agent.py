import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from livekit.agents import llm

from packages.shared.settings import Settings
from packages.voice.agent import MedicalLLM, prepare_report


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
        settings = SimpleNamespace(groq_model="test")

        async def answer(self, query, report, history, on_stage):
            assert query == "Explain hemoglobin"
            assert report == {"sample": True}
            assert history == [{"role": "assistant", "text": "Welcome"}]
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
    await model.aclose()


async def test_agent_cancellation_does_not_emit_answer():
    entered = asyncio.Event()
    events = []

    async def publish(event):
        events.append(event)

    class SlowPipeline:
        settings = SimpleNamespace(groq_model="test")

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
        settings = SimpleNamespace(groq_model="test")

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
