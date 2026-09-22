import json
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants
from pydantic import BaseModel, Field

from packages.shared.reports import load_report
from packages.shared.settings import Settings
from packages.shared.store import SessionStore
from packages.voice.pipeline import Pipeline, PipelineError


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    store = SessionStore(config.database_path, config.session_ttl_seconds)
    sample = load_report(config.report_context_path)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=config.request_timeout_seconds) as client:
            app.state.http_client = client
            yield

    app = FastAPI(title="MediVoice", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_url],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "demo_mode": config.demo_mode,
            "missing_voice_settings": config.missing(),
            "missing_text_settings": config.missing(False),
            "credentials_verified": False,
        }

    @app.post("/api/sessions")
    def create_session():
        sid = store.create(sample)
        return {"session_id": sid, "report": sample, "expires_in": config.session_ttl_seconds}

    def get_report(sid):
        report = store.get(sid)
        if report is None:
            raise HTTPException(404, "Session expired or not found. Start a new conversation.")
        return report

    @app.post("/api/sessions/{sid}/token")
    def token(sid: str):
        get_report(sid)
        if config.demo_mode:
            raise HTTPException(
                409, "Demo mode supports simulated text only; disable it for voice."
            )
        if missing := config.missing():
            raise HTTPException(503, "Missing configuration: " + ", ".join(missing))
        room = f"medivoice-{sid}"
        jwt = (
            AccessToken(
                config.livekit_api_key.get_secret_value(),
                config.livekit_api_secret.get_secret_value(),
            )
            .with_identity(f"patient-{sid}")
            .with_name("MediVoice guest")
            .with_ttl(timedelta(minutes=10))
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_room_config(
                RoomConfiguration(
                    agents=[
                        RoomAgentDispatch(
                            agent_name="medivoice-agent", metadata=json.dumps({"session_id": sid})
                        )
                    ]
                )
            )
            .to_jwt()
        )
        return {"server_url": config.livekit_url, "participant_token": jwt, "room_name": room}

    @app.post("/api/sessions/{sid}/message")
    async def message(sid: str, body: Message):
        report = get_report(sid)
        try:
            # Text test calls are single-turn; never share mutable language state.
            return await Pipeline(config, app.state.http_client).answer(body.text, report)
        except PipelineError as exc:
            raise HTTPException(502, str(exc)) from None

    return app


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")


app = create_app()
