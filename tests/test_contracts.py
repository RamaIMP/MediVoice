import pytest
from pydantic import ValidationError

from packages.contracts import ReportContext
from packages.shared.reports import load_report
from packages.shared.settings import Settings


def test_shared_sample_uses_report_contract():
    report = load_report(Settings(_env_file=None).report_context_path)
    assert report["is_sample"] is True
    assert report["schema_version"] == "1.0"
    assert report["findings"][0]["value"] == 9.2


def test_raw_ocr_requires_explicit_mapping():
    with pytest.raises(ValidationError):
        ReportContext.model_validate({"content": {"key_values": {}}})
