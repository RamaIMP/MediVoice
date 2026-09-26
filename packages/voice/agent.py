"""Default: local console. Explicit `dev` connects to LiveKit for browser testing."""

import asyncio
import json
import logging
import time
import uuid

import httpx
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    inference,
    llm,
    room_io,
    tts,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins import assemblyai, cartesia, elevenlabs, noise_cancellation, silero

from packages.shared.debug_log import setup_console_logging, trace, turn
from packages.shared.reports import load_report
from packages.shared.settings import BASE, Settings
from packages.shared.store import SessionStore
from packages.voice.pipeline import Pipeline, PipelineError

log = logging.getLogger("medivoice")
server = AgentServer()


def voice_room_options(config, *, console):
    # Room filters require LiveKit Cloud audio; local console stays independent.
    if console or not config.background_voice_cancellation:
        return {}
    return {"room_options": room_io.RoomOptions(
        audio_input=room_io.AudioInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )}


def trace_conversation_item(event):
    """Conversation events also include handoffs, which have no message role/text."""
    item = event.item
    if not isinstance(item, llm.ChatMessage):
        trace("conversation_event", item_type=getattr(item, "type", type(item).__name__))
        return
    trace("conversation_item", role=item.role, text=item.text_content,
          interrupted=getattr(item, "interrupted", False))


class MedicalLLM(llm.LLM):
    def __init__(self, pipeline, report, publish):
        super().__init__()
        self.pipeline, self.report, self.publish = pipeline, report, publish

    @property
    def model(self):
        return self.pipeline.settings.groq_model

    @property
    def provider(self):
        return f"{self.pipeline.settings.language_provider}-groq"

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS, **kwargs):
        return MedicalStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class MedicalStream(llm.LLMStream):
    async def _run(self):
        owner = self._llm
        messages = [
            {"role": item.role, "text": item.text_content[:2000]}
            for item in self._chat_ctx.items
            if isinstance(item, llm.ChatMessage)
            and item.role in ("user", "assistant")
            and item.text_content
        ]
        if not messages or messages[-1]["role"] != "user":
            return
        # Once Doctor Connect opens, booking choices must come from the screen.
        # Ignore microphone turns completely so ambient speech cannot select a
        # doctor, provide a date/time, or be mistaken for a patient's name.
        if getattr(owner.pipeline, "care_state", {"stage": "closed"})["stage"] != "closed":
            trace("doctor_connect_voice_ignored")
            return
        turn_id = uuid.uuid4().hex
        trace_token = turn.set(turn_id)
        transcript_id = next(item.id for item in reversed(self._chat_ctx.items)
                             if isinstance(item, llm.ChatMessage) and item.role == "user")

        async def stage(payload):
            if payload.get("type") == "user_transcript":
                await owner.publish({**payload, "id": transcript_id, "turn_id": turn_id})
                return
            await owner.publish({"type": "stage", "turn_id": turn_id, **payload})

        try:
            result = await owner.pipeline.answer(
                messages[-1]["text"], owner.report, messages[:-1], on_stage=stage
            )
            if "care_state" in result:
                await owner.publish({"type": "doctor_connect", "state": result["care_state"]})
            await owner.publish(
                {
                    "type": "answer_ready",
                    "turn_id": turn_id,
                    "language": result["language"],
                    "timings_ms": result["timings_ms"],
                }
            )
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id=turn_id, delta=llm.ChoiceDelta(role="assistant", content=result["text"])
                )
            )
        except asyncio.CancelledError:
            trace("turn_cancelled")
            # AgentSession cancels generation on interruption; never publish stale answers.
            raise
        except PipelineError as exc:
            # PipelineError messages are sanitized by the pipeline. Do not log raw
            # provider responses or exception chains containing patient data/URLs.
            log.warning("Answer pipeline failed (turn_id=%s): %s", turn_id, str(exc))
            trace("pipeline_error", message=str(exc))
            await owner.publish({"type": "error", "message": str(exc)})
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id=turn_id,
                    delta=llm.ChoiceDelta(
                        role="assistant",
                        content={
                            "hi": "माफ़ कीजिए, अभी आपका सवाल पूरा नहीं कर पाया। कृपया फिर से पूछिए।",
                        }.get(getattr(owner.pipeline, "response_language", None),
                              "Sorry, I could not complete that request. Please try again."),
                    ),
                )
            )
        finally:
            turn.reset(trace_token)


def build_tts(config):
    if config.tts_provider == "cartesia_direct":
        provider = cartesia.TTS(
            model=config.cartesia_model.removeprefix("cartesia/"),
            voice=config.cartesia_voice_id,
            api_key=config.cartesia_api_key.get_secret_value(),
            # Sonic word timestamps are only available for a small set of
            # languages. MediVoice does not consume them, and requesting them
            # can leave non-English streams without audio frames.
            word_timestamps=False,
        )
        return provider, provider
    if config.tts_provider == "cartesia_livekit":
        provider = inference.TTS(
            model=config.cartesia_model,
            voice=config.cartesia_voice_id,
            # Use the SDK inference gateway, not the project's WebRTC room URL.
            api_key=config.livekit_api_key.get_secret_value(),
            api_secret=config.livekit_api_secret.get_secret_value(),
        )
        return provider, provider
    provider = elevenlabs.TTS(
        api_key=config.elevenlabs_api_key.get_secret_value(),
        voice_id=config.elevenlabs_voice_id,
        model=config.elevenlabs_model,
        encoding="mp3_44100_128",
    )
    # SDK 1.6's ElevenLabs streaming path uses WebSockets, unsupported by eleven_v3.
    # HTTP synthesize is wrapped sentence-by-sentence for LiveKit instead.
    return provider, tts.StreamAdapter(tts=provider)


async def prepare_report(ctx: JobContext, config: Settings) -> dict:
    """Local console uses the fixture and never connects to a LiveKit room."""
    console = ctx.is_fake_job()
    if missing := config.missing(console=console):
        raise RuntimeError("Missing configuration: " + ", ".join(missing))
    if console:
        return load_report(config.report_context_path)
    metadata = json.loads(ctx.job.metadata or "{}")
    sid = metadata.get("session_id", "")
    store = SessionStore(config.database_path, config.session_ttl_seconds)
    report = store.get(sid)
    if report is None:
        raise RuntimeError("Report session is missing or expired. Start through the web app.")

    await ctx.connect()
    return report


@server.rtc_session(agent_name="medivoice-agent")
async def entrypoint(ctx: JobContext):
    config = Settings()
    console = ctx.is_fake_job()
    if console:
        setup_console_logging(config)
    report = await prepare_report(ctx, config)
    if console:
        log.info("Local console: no LiveKit room connection. Provider quotas still apply.")
    log.info("TTS provider: %s", config.tts_provider)
    if config.tts_provider == "cartesia_livekit":
        log.info("Cartesia Sonic via LiveKit Inference: LiveKit usage applies, including console.")
    elif config.tts_provider == "cartesia_direct":
        log.info("Cartesia Sonic direct: Cartesia credits apply; no LiveKit Inference TTS usage.")
    pending: set[asyncio.Task] = set()

    async def publish(payload):
        if config.tts_provider in ("cartesia_livekit", "cartesia_direct") and payload.get("type") == "answer_ready":
            voice.update_options(language=payload["language"])
        trace("agent_event", **payload)
        if console:
            # Provider errors are already sanitized by PipelineError.
            if payload.get("type") == "error":
                log.warning("MediVoice: %s", payload["message"])
            elif payload.get("type") == "stage":
                log.info("Stage %s: %s", payload["stage"], payload["status"])
            return
        try:
            await ctx.room.local_participant.publish_data(
                json.dumps(payload).encode(), reliable=True, topic="medivoice"
            )
        except Exception:
            log.debug("Could not send UI event; room may have closed.")

    def schedule(payload):
        task = asyncio.create_task(publish(payload))
        pending.add(task)
        task.add_done_callback(pending.discard)

    client = httpx.AsyncClient(timeout=config.request_timeout_seconds)
    speech = assemblyai.STT(
        api_key=config.assemblyai_api_key.get_secret_value(),
        model=config.assemblyai_model,
        language_detection=True,
        format_turns=False,
    )
    provider, voice = build_tts(config)
    pipeline = Pipeline(config, client)
    session = AgentSession(
        stt=speech,
        vad=silero.VAD.load(
            activation_threshold=config.vad_activation_threshold,
            min_speech_duration=config.vad_min_speech_duration,
            min_silence_duration=0.55,
        ),
        llm=MedicalLLM(pipeline, report, publish),
        tts=voice,
        turn_handling=TurnHandlingOptions(
            # Appointment changes must not run on speculative user turns.
            preemptive_generation={"enabled": False},
            turn_detection="stt",
            interruption={
                "enabled": True,
                "mode": "vad",
                "min_duration": config.interruption_min_duration,
                "min_words": 1,
                "false_interruption_timeout": 1.0,
                "resume_false_interruption": True,
            },
            endpointing={"mode": "fixed", "min_delay": 0.5, "max_delay": 2.0},
        ),
    )
    user_stopped = None
    ending = False
    timeout_tasks: set[asyncio.Task] = set()

    def track_timeout(task):
        timeout_tasks.add(task)
        task.add_done_callback(timeout_tasks.discard)
        return task

    async def end_voice_session(message: str):
        """Close the whole room so an abandoned browser cannot keep metered audio alive."""
        nonlocal ending
        if ending:
            return
        ending = True
        log.info("Ending voice session: %s", message)
        await publish({"type": "session_expired", "message": message})
        # DeleteRoom disconnects both the browser participant and this agent.
        await ctx.delete_room()
        ctx.shutdown(message)

    def reset_idle_timeout():
        if console or ending:
            return
        for task in tuple(timeout_tasks):
            if task.get_name() == "idle-call-timeout":
                task.cancel()

        async def expire_when_idle():
            warning_seconds = min(15, config.idle_call_timeout_seconds // 4)
            await asyncio.sleep(config.idle_call_timeout_seconds - warning_seconds)
            if ending:
                return
            await publish({
                "type": "session_warning",
                "message": f"No speech detected. This call will end in {warning_seconds} seconds.",
            })
            await asyncio.sleep(warning_seconds)
            await end_voice_session(
                f"This call ended after {config.idle_call_timeout_seconds} seconds without speech."
            )

        track_timeout(asyncio.create_task(expire_when_idle(), name="idle-call-timeout"))

    def start_call_timeouts():
        if console:
            return

        async def expire_at_call_limit():
            warning_seconds = min(15, config.max_call_duration_seconds // 4)
            await asyncio.sleep(config.max_call_duration_seconds - warning_seconds)
            if ending:
                return
            await publish({
                "type": "session_warning",
                "message": f"This call will end in {warning_seconds} seconds.",
            })
            await asyncio.sleep(warning_seconds)
            await end_voice_session(
                f"This call reached the {config.max_call_duration_seconds}-second limit."
            )

        track_timeout(asyncio.create_task(expire_at_call_limit(), name="max-call-duration"))
        reset_idle_timeout()

    # Only the patient bound to this room can submit touch/text actions.
    command_busy = False

    async def care_input(packet):
        nonlocal command_busy
        if command_busy:
            await publish({"type": "error", "message": "Please wait for the current selection to finish."})
            await publish({"type": "doctor_connect", "state": pipeline.care_state})
            return
        command_busy = True
        try:
            data = json.loads(packet.data)
            if data.get("type") == "sync":
                await publish({"type": "doctor_connect", "state": pipeline.care_state})
                return
            if data.get("revision") != pipeline.care_state["revision"]:
                await publish({"type": "doctor_connect", "state": pipeline.care_state})
                return
            action = data.get("action", {})
            kind = action.get("type")
            await session.interrupt()
            mapping = {"select": "select", "close": "cancel", "edit": "edit", "search": "search",
                       "search_location": "search_location", "yes": "yes", "decline": "decline",
                       "set_date": "set_date", "set_time": "set_time", "set_patient": "set_patient",
                       "edit_patient": "edit_patient", "back": "back",
                       "select_touch": "select_touch", "set_patient_touch": "set_patient_touch"}
            if kind not in mapping:
                return
            value = action.get("area", "") if kind == "search" else action.get("id", "") if kind in ("select", "select_touch") else ""
            if kind.startswith("set_"):
                value = action.get("value", "")
            if kind == "search_location":
                value = action.get("location")
                if not isinstance(value, dict):
                    return
            elif not isinstance(value, str) or len(value) > 100:
                return
            result = await pipeline.care_command(mapping[kind], value, data["revision"])
            await publish({"type": "doctor_connect", "state": result["care_state"]})
            command_busy = False
            if config.tts_provider in ("cartesia_livekit", "cartesia_direct"):
                voice.update_options(language=pipeline.response_language or "en")
            await session.say(result["text"])
        except (ValueError, TypeError, KeyError, AttributeError):
            pass  # Malformed room data is not a user utterance.
        except PipelineError as exc:
            await publish({"type": "error", "message": str(exc)})
        finally:
            command_busy = False
            await publish({"type": "doctor_connect", "state": pipeline.care_state})

    if not console:
        sid = json.loads(ctx.job.metadata or "{}").get("session_id", "")

        @ctx.room.on("data_received")
        def care_packet(packet):
            if (packet.topic != "medivoice.care" or not packet.participant
                    or packet.participant.identity != f"patient-{sid}"
                    or len(packet.data) > 2048):
                return
            task = asyncio.create_task(care_input(packet))
            pending.add(task)
            task.add_done_callback(pending.discard)

    session.on("conversation_item_added", trace_conversation_item)

    @session.on("user_input_transcribed")
    def transcription(event):
        trace("stt_transcript", text=event.transcript, is_final=event.is_final,
              language=getattr(event, "language", None))
        if event.is_final and event.transcript.strip():
            reset_idle_timeout()

    @session.on("metrics_collected")
    def metrics(event):
        trace("voice_metrics", metrics=event.metrics.model_dump(mode="json"))

    @session.on("user_state_changed")
    def user_state(event):
        nonlocal user_stopped
        if event.old_state == "speaking" and event.new_state != "speaking":
            user_stopped = time.perf_counter()

    @session.on("agent_state_changed")
    def agent_state(event):
        nonlocal user_stopped
        schedule({"type": "agent_state", "state": event.new_state})
        if event.new_state == "speaking" and user_stopped is not None:
            schedule(
                {
                    "type": "latency",
                    "speech_end_to_agent_speaking_ms": round(
                        (time.perf_counter() - user_stopped) * 1000
                    ),
                }
            )
            user_stopped = None

    @session.on("error")
    def error(event):
        trace("voice_error", error=str(event.error))
        schedule(
            {
                "type": "error",
                "message": "A voice provider failed. Check the worker "
                "and provider configuration, then reconnect.",
            }
        )

    async def cleanup():
        current = asyncio.current_task()
        for task in tuple(timeout_tasks):
            if task is not current:
                task.cancel()
        await asyncio.gather(*(task for task in timeout_tasks if task is not current), return_exceptions=True)
        await session.aclose()
        await speech.aclose()
        await voice.aclose()
        if provider is not voice:
            await provider.aclose()
        await client.aclose()
        for task in list(pending):
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    ctx.add_shutdown_callback(cleanup)
    await session.start(
        **voice_room_options(config, console=console),
        **({} if console else {"room": ctx.room}),
        agent=Agent(
            instructions="You are MediVoice, a friendly medical-report explanation assistant."
        ),
    )
    start_call_timeouts()
    await session.say(
        "Welcome to MediVoice. You can ask about your report in English or Hindi."
    )


def main():
    # The SDK reads LiveKit settings from environment; Settings reads the same local .env.
    import sys

    from dotenv import load_dotenv

    load_dotenv(BASE / ".env")
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) == 1:
        sys.argv.append("console")
    if "console" in sys.argv:
        setup_console_logging(Settings())
    agents.cli.run_app(server)
