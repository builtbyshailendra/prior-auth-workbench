"""Shapes of what the API accepts. The connectors send exactly this (see connectors/src/canonical.ts)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemberIn(Strict):
    id: str = Field(max_length=20)
    name: str = Field(default="", max_length=100)


class ProviderIn(Strict):
    npi: str = Field(max_length=10)
    name: str = Field(default="", max_length=120)


class ServiceIn(Strict):
    code: str = Field(max_length=10)
    diagnosis_codes: list[str] = Field(max_length=12)
    date_start: date
    date_end: date | None = None


class DocumentIn(Strict):
    doc_type: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)


class IntakeRequest(Strict):
    """One prior-authorization request in the internal format, whatever channel it came from."""

    source: Literal["fhir", "x12", "fax", "crm", "api"]
    source_id: str = Field(min_length=1, max_length=128)
    received_at: datetime | None = None  # when the source received it; the clock starts here
    priority: Literal["standard", "expedited"] = "standard"
    member: MemberIn
    provider: ProviderIn
    service: ServiceIn
    documents: list[DocumentIn] = Field(default_factory=list, max_length=50)


class DocumentsIn(Strict):
    documents: list[DocumentIn] = Field(min_length=1, max_length=50)
