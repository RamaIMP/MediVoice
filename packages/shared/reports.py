"""Shared report loader for console and API. Does not perform OCR."""
import json
from pathlib import Path

from packages.contracts import ReportContext


def load_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Report JSON must be an object")
    # Qwen's clean medical JSON is already the format supplied to the voice LLM.
    # Keep it unchanged: no CBC-only findings adapter is required.
    if {"patient", "lab", "doctors", "pages"}.issubset(report):
        return report
    return ReportContext.model_validate(report).model_dump()
