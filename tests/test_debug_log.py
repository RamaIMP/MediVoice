import json
import logging
import sys

from pydantic import SecretStr

from packages.shared import debug_log
from packages.shared.settings import Settings


def test_debug_file_private_redacted_and_contains_trace(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(debug_log, "enabled", False)
    config = Settings(_env_file=None, console_log_dir=tmp_path,
                      gemini_api_key=SecretStr("private-test-key"))
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.DEBUG)
    existing = list(root.handlers)
    try:
        path = debug_log.setup_console_logging(config)
        assert debug_log.setup_console_logging(config) == path
        token = debug_log.turn.set("turn-123")
        try:
            debug_log.trace("translation", text="हीमोग्लोबिन private-test-key")
            try:
                raise ValueError("private-test-key")
            except ValueError:
                logging.getLogger("medivoice").exception("provider error")
        finally:
            debug_log.turn.reset(token)
        from pathlib import Path
        saved = Path(path).read_text()
        assert "private-test-key" not in saved
        assert "[REDACTED]" in saved
        assert "हीमोग्लोबिन" in saved
        rows = [json.loads(line) for line in saved.splitlines()]
        assert any(row["turn_id"] == "turn-123" for row in rows)
        assert any("exception" in row for row in rows)
        assert Path(path).stat().st_mode & 0o777 == 0o600
    finally:
        for handler in list(root.handlers):
            if handler not in existing:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(old_level)
        logging.captureWarnings(False)


def test_disabled_debug_does_not_create_directory(tmp_path):
    path = tmp_path / "disabled"
    assert debug_log.setup_console_logging(
        Settings(_env_file=None, console_debug=False, console_log_dir=path)) is None
    assert not path.exists()
