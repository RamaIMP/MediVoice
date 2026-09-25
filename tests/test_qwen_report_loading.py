import json

from packages.shared.reports import load_report
from packages.voice.guardrails import numeric_grounded


def test_clean_qwen_report_is_passed_through_unchanged(tmp_path):
    report = {
        "patient": {"name": "Sample", "age": "35", "sex": "Female"},
        "lab": {"name": "Example lab", "address": None},
        "doctors": [],
        "pages": [{"page_number": 1, "tables": [{"title": "CBC",
                   "columns": ["Test", "Result"], "rows": [["Hb", "12.6"]]}],
                   "notes": [], "uncertainties": []}],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert load_report(path) == report


def test_numeric_guardrail_reads_qwen_page_tables():
    report = {"patient": {}, "lab": {}, "doctors": [], "pages": [
        {"page_number": 1, "tables": [
            {"rows": [["Hb", "12.6", "12.0 - 15.0"]]}
        ]}
    ]}
    assert numeric_grounded("Hemoglobin is 12.6 g/dL.", report)
    assert not numeric_grounded("Hemoglobin is 99 g/dL.", report)
