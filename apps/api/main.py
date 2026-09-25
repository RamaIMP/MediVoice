import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants
from pydantic import BaseModel, Field

from packages.knowledge.qwen_pdf_to_json import ReportExtractionError, extract_medical_report_bytes
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

    @app.post("/api/reports")
    async def upload_report(file: UploadFile = File(...)):
        accepted = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
        content_type = file.content_type or ""
        if content_type not in accepted:
            raise HTTPException(415, "Choose a PDF, JPG, PNG, or WebP report.")
        content = await file.read(config.report_upload_max_bytes + 1)
        await file.close()
        if len(content) > config.report_upload_max_bytes:
            raise HTTPException(413, "Choose a report smaller than 10 MB.")
        key = config.groq_api_key.get_secret_value()
        if not key:
            raise HTTPException(503, "Report analysis is not configured. Add GROQ_API_KEY and try again.")
        try:
            report = await asyncio.to_thread(
                extract_medical_report_bytes,
                content,
                file.filename or "medical-report",
                content_type,
                key,
                max_pages=config.report_upload_max_pages,
            )
        except ReportExtractionError as exc:
            if exc.status_code == 429:
                raise HTTPException(
                    429,
                    "Report processing has reached its temporary usage limit. Please wait a minute and try again.",
                ) from None
            raise HTTPException(502, "The report-processing service is temporarily unavailable. Please try again.") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(502, "We could not read that report. Please try a clear image or PDF again.") from None
        sid = store.create(report)
        return {
            "session_id": sid,
            "expires_in": config.session_ttl_seconds,
            "report_summary": {
                "processed_page_count": report["processed_page_count"],
                "lab_name": report.get("lab", {}).get("name"),
            },
        }

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
