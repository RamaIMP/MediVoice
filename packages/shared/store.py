"""Shared local session storage for the API and separately running agent worker."""

import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class SessionStore:
    def __init__(self, path: Path, ttl: int = 3600):
        self.path, self.ttl = path, ttl
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(id TEXT PRIMARY KEY, report TEXT NOT NULL, expires REAL NOT NULL)"
            )
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, report: dict) -> str:
        sid = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires <= ?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (sid, json.dumps(report), time.time() + self.ttl),
            )
        return sid

    def get(self, sid: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT report FROM sessions WHERE id=? AND expires>?", (sid, time.time())
            ).fetchone()
        return json.loads(row[0]) if row else None
