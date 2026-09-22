"""Versioned integration contracts. No provider or application dependencies."""
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ReportFinding(BaseModel):
    parameter: str
    value: float | str
    unit: str
    reference_range: str
    status: str | None = None


class ReportContext(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: str
    report_type: str
    is_sample: bool = False
    description: str = ""
    findings: list[ReportFinding]
    source_pages: list[int] = Field(default_factory=list)


class DoctorSearchRequest(BaseModel):
    specialty: str
    location: str
    # Do not obtain location without the user's permission.


class DoctorSearchResult(BaseModel):
    name: str
    address: str
    contact_url: str | None = None


class KnowledgeExtractor(Protocol):
    async def extract(self, document: bytes, mime_type: str) -> ReportContext: ...


class DoctorSearch(Protocol):
    async def search(self, request: DoctorSearchRequest) -> list[DoctorSearchResult]: ...
