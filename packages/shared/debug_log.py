"""Local console diagnostics. Contains conversation data: never upload publicly."""

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from pydantic import SecretStr

turn = ContextVar("debug_turn", default=None)
enabled = False


class SafeFormatter(logging.Formatter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def format(self, record):
        data = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname, "logger": record.name,
            "message": record.getMessage(), "turn_id": turn.get(),
        }
        reserved = logging.makeLogRecord({}).__dict__
        data["details"] = {k: v for k, v in record.__dict__.items()
                           if k not in reserved and k not in ("message", "asctime")}
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        output = json.dumps(data, ensure_ascii=False, default=str)
        for secret in self.secrets:
            output = output.replace(secret, "[REDACTED]")
        return output


def setup_console_logging(config):
    global enabled
    if not config.console_debug:
        return None
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "medivoice_debug", False):
            return handler.baseFilename
    directory = config.console_log_dir
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (datetime.now().strftime("console-%Y%m%d-%H%M%S-")
                        + uuid.uuid4().hex[:8] + ".jsonl")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    handler = RotatingFileHandler(path, maxBytes=10_000_000, backupCount=3, encoding="utf-8")
    # Rotated files must retain private permissions, including the new active file.
    def private_open():
        fd = os.open(handler.baseFilename, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        return os.fdopen(fd, "a", encoding="utf-8")
    handler._open = private_open
    handler.medivoice_debug = True
    secrets = [v.get_secret_value() for v in config.__dict__.values() if isinstance(v, SecretStr)]
    handler.setFormatter(SafeFormatter(secrets))
    handler.setLevel(logging.DEBUG)
    root.addHandler(handler)
    logging.captureWarnings(True)
    previous_hook = sys.excepthook

    def exception_hook(exc_type, value, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logging.getLogger("medivoice").critical(
                "Unhandled console exception", exc_info=(exc_type, value, tb))
        previous_hook(exc_type, value, tb)

    sys.excepthook = exception_hook
    enabled = True
    logging.getLogger("medivoice").info("Private debug log: %s", path)
    return str(path)


def trace(event, **data):
    if enabled:
        logging.getLogger("medivoice.trace").info(event, extra={"trace": data})
