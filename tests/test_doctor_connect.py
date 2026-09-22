import asyncio
import json

import httpx
import pytest

from packages.doctor_connect.demo import initial_state, transition
from packages.shared.settings import Settings
from packages.voice.pipeline import Pipeline, PipelineError


def settings():
    return Settings(_env_file=None, gemini_api_key="test", groq_api_key="test")


def reply(action, value="", language="en"):
    text = json.dumps(dict(language=language, english_query="request", care_action=action,
                           care_value=value, scope="doctor_connect"))
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_booking_cannot_skip_confirmation_and_fallbacks():
    for i, channel in [(1, "WhatsApp"), (2, "Phone"), (3, "Appointment page")]:
        state, _ = transition(initial_state(), "search")
        state, _ = transition(state, "select", f"demo-{i}")
        unchanged, _ = transition(state, "set_time", "10 am")
        assert unchanged["stage"] == "confirm"
        for action, value in [("yes", ""), ("set_date", "tomorrow"), ("set_time", "10 am"),
                              ("set_patient", "Demo patient"), ("yes", "")]:
            state, text = transition(state, action, value)
        assert state["stage"] == "review" and channel in text
        state, text = transition(state, "yes")
        assert state["stage"] == "handoff" and "Nothing has been sent or booked" in text


async def test_voice_and_touch_share_state_without_medical_model():
    actions = iter([("search", ""), ("yes", ""), ("set_date", "tomorrow"),
                    ("set_time", "10 am"), ("set_patient", "Demo patient"), ("yes", ""), ("yes", "")])

    def handler(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        payload = json.loads(body["contents"][0]["parts"][0]["text"])
        assert "care_state" in payload
        return reply(*next(actions))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p = Pipeline(settings(), client)
        result = await p.answer("Could you help me arrange a consultation?", {})
        assert result["care_state"]["stage"] == "search"
        result = await p.care_command("select", "demo-1", 1)
        assert result["care_state"]["stage"] == "confirm"
        for query in ["yes", "tomorrow", "10 am", "Demo patient", "yes", "yes"]:
            result = await p.answer(query, {})
        assert result["care_state"]["stage"] == "handoff"
        assert "WhatsApp" in result["text"]
        assert Pipeline(settings(), client).care_state["stage"] == "closed"
        with pytest.raises(PipelineError, match="changed"):
            await p.care_command("select", "demo-2", 1)


async def test_cancelled_translation_does_not_advance_booking():
    entered = asyncio.Event()

    async def handler(request):
        body = json.loads(request.content)
        if body["generationConfig"].get("responseMimeType"):
            return reply("search", language="hi")
        entered.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        p = Pipeline(settings(), client)
        task = asyncio.create_task(p.answer("डॉक्टर ढूंढो", {}))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert p.care_state == initial_state()


async def test_invalid_doctor_id_never_becomes_selection():
    async with httpx.AsyncClient() as client:
        p = Pipeline(settings(), client)
        await p.care_command("search", "", 0)
        result = await p.care_command("select", "untrusted-number", 1)
        assert result["care_state"]["selected"] is None
        assert result["care_state"]["stage"] == "search"
