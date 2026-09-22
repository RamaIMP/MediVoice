"""Shared report loader for console and API. Does not perform OCR."""
import json
from pathlib import Path

from packages.contracts import ReportContext


def load_report(path: Path) -> dict:
    return ReportContext.model_validate(json.loads(path.read_text())).model_dump()
