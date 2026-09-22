import base64
import json
import time

from fastapi.testclient import TestClient

from apps.api.main import create_app
from packages.shared.settings import Settings
from packages.shared.store import SessionStore


def test_text_sessions_do_not_share_language_state(tmp_path, monkeypatch):
    from apps.api import main

    class FakePipeline:
        def __init__(self, config, client):
            self.response_language = None

        async def answer(self, query, report):
            assert self.response_language is None
            self.response_language = query
            return {"language": query, "text": "test"}

    monkeypatch.setattr(main, "Pipeline", FakePipeline)
    with TestClient(create_app(settings(tmp_path))) as client:
        for language in ("hi", "en"):
            sid = client.post("/api/sessions").json()["session_id"]
            response = client.post(f"/api/sessions/{sid}/message", json={"text": language})
            assert response.status_code == 200
            assert response.json()["language"] == language


def settings(tmp_path, **kwargs):
    return Settings(_env_file=None, database_path=tmp_path / "sessions.db", **kwargs)


def test_missing_keys_block_voice_without_returning_secrets(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        response = client.post(f"/api/sessions/{sid}/token")
        assert response.status_code == 503
        assert "ELEVENLABS_API_KEY" in response.json()["detail"]
        assert client.post("/api/sessions/unknown/token").status_code == 404


def test_room_token_dispatch_is_bound_to_session(tmp_path):
    config = settings(
        tmp_path,
        livekit_url="wss://example.livekit.cloud",
        livekit_api_key="testkey",
        livekit_api_secret="a" * 40,
        gemini_api_key="test",
        groq_api_key="test",
        assemblyai_api_key="test",
        elevenlabs_api_key="test",
    )
    with TestClient(create_app(config)) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        data = client.post(f"/api/sessions/{sid}/token").json()
        payload = data["participant_token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        assert claims["video"]["room"] == f"medivoice-{sid}"
        dispatch = claims["roomConfig"]["agents"][0]
        assert dispatch["agentName"] == "medivoice-agent"
        assert json.loads(dispatch["metadata"])["session_id"] == sid
        assert claims["exp"] - claims["nbf"] <= 600
        assert "a" * 40 not in json.dumps(data)


def test_demo_explicitly_simulated_and_voice_disabled(tmp_path):
    with TestClient(create_app(settings(tmp_path, demo_mode=True))) as client:
        sid = client.post("/api/sessions").json()["session_id"]
        result = client.post(f"/api/sessions/{sid}/message", json={"text": "Hello"})
        assert result.json()["simulated"] is True
        assert client.post(f"/api/sessions/{sid}/token").status_code == 409
        assert client.post(f"/api/sessions/{sid}/message", json={"text": " "}).status_code == 422


def test_worker_can_read_session_and_expired_session_is_rejected(tmp_path):
    path = tmp_path / "sessions.db"
    first = SessionStore(path)
    sid = first.create({"report_id": "sample"})
    second = SessionStore(path)
    assert second.get(sid) == {"report_id": "sample"}
    with first.connect() as db:
        db.execute("UPDATE sessions SET expires=? WHERE id=?", (time.time() - 1, sid))
    assert second.get(sid) is None
