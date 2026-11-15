"""Tables. Key rules are also database constraints, so a bug in the API can't break them."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    DDL,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

STATES = (
    "received",
    "pended",
    "ready_for_review",
    "in_nurse_review",
    "escalated",
    "approved",
    "denied",
    "closed_no_auth",
    "closed_ineligible",
    "withdrawn",
)
OPEN_STATES = ("received", "pended", "ready_for_review", "in_nurse_review", "escalated")
PRIORITIES = ("standard", "expedited")
SOURCES = ("fhir", "x12", "fax", "crm", "api")
EXTRACTION_STATUSES = ("not_started", "pending", "complete", "manual_needed", "not_applicable")
ROLES = ("intake_coordinator", "nurse_reviewer", "medical_director", "admin")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    """A person who signs in. Services use API tokens instead (see app/auth.py)."""

    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_one_of("role", ROLES), name="role_is_known"),)

    username: Mapped[str] = mapped_column(String(40), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Member(Base):
    """A copy of the core admin system's member list (synthetic). Read-only for this service."""

    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date] = mapped_column(Date)


class Coverage(Base):
    __tablename__ = "coverage_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    plan: Mapped[str] = mapped_column(String(40))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date | None] = mapped_column(Date)


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint(_one_of("state", STATES), name="state_is_known"),
        CheckConstraint(_one_of("priority", PRIORITIES), name="priority_is_known"),
        CheckConstraint(_one_of("extraction_status", EXTRACTION_STATUSES), name="extraction_status_is_known"),
        # A decided case records who decided and when.
        CheckConstraint(
            "state NOT IN ('approved', 'denied') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="decision_has_who_and_when",
        ),
        # A denial always carries a reason code and an explanation (CMS-0057-F asks for a reason).
        CheckConstraint(
            "state <> 'denied' OR (decision_reason_code IS NOT NULL AND decision_explanation IS NOT NULL)",
            name="denial_has_reason",
        ),
        # At most one open case per member + provider + service + start date. Duplicates are linked instead.
        Index(
            "one_open_case_per_request",
            "business_key",
            unique=True,
            postgresql_where=text(_one_of("state", OPEN_STATES)),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_key: Mapped[str] = mapped_column(String(64), index=True)
    member_id: Mapped[str] = mapped_column(String(20), index=True)
    member_name: Mapped[str] = mapped_column(String(100), default="")
    provider_npi: Mapped[str] = mapped_column(String(10))
    provider_name: Mapped[str] = mapped_column(String(120), default="")
    service_code: Mapped[str] = mapped_column(String(10))
    diagnosis_codes: Mapped[list[str]] = mapped_column(JSONB)
    service_date_start: Mapped[date] = mapped_column(Date)
    service_date_end: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    catalogue_version: Mapped[str] = mapped_column(String(20))
    rfi_count: Mapped[int] = mapped_column(Integer, default=0)
    extraction_status: Mapped[str] = mapped_column(String(20), default="not_started")
    extraction_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_to: Mapped[str | None] = mapped_column(String(40))
    decided_by: Mapped[str | None] = mapped_column(String(40))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason_code: Mapped[str | None] = mapped_column(String(40))
    decision_explanation: Mapped[str | None] = mapped_column(Text)
    escalation_note: Mapped[str | None] = mapped_column(Text)
    closed_reason: Mapped[str | None] = mapped_column(Text)

    documents: Mapped[list[Document]] = relationship(back_populates="case", order_by="Document.id")
    submissions: Mapped[list[Submission]] = relationship(back_populates="case", order_by="Submission.id")
    rfis: Mapped[list[Rfi]] = relationship(back_populates="case", order_by="Rfi.id")
    facts: Mapped[list[Fact]] = relationship(back_populates="case", order_by="Fact.id")


class Submission(Base):
    """One incoming message. The (source, source_id) pair makes replays harmless."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="one_submission_per_source_message"),
        CheckConstraint(_one_of("source", SOURCES), name="source_is_known"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    source: Mapped[str] = mapped_column(String(10))
    source_id: Mapped[str] = mapped_column(String(128))
    trace_id: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[Case] = relationship(back_populates="submissions")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[Case] = relationship(back_populates="documents")


class Rfi(Base):
    """A request for more information sent to the provider, listing everything missing at once."""

    __tablename__ = "rfis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    items: Mapped[list[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="rfis")


class Fact(Base):
    """One checklist fact for a case, with where it came from.

    method: ai (Claude), rules (the baseline) or manual (a person).
    status: verified (quote checked), not_documented, dropped (failed checks) or entered (by a person).
    """

    __tablename__ = "facts"
    __table_args__ = (
        CheckConstraint("method IN ('ai', 'rules', 'manual')", name="fact_method_is_known"),
        CheckConstraint("status IN ('verified', 'not_documented', 'dropped', 'entered')", name="fact_status_is_known"),
        # A verified fact always has its quote. That is the whole point.
        CheckConstraint("status <> 'verified' OR quote IS NOT NULL", name="verified_fact_has_quote"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    field: Mapped[str] = mapped_column(String(40))
    value: Mapped[object] = mapped_column(JSONB, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    method: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    entered_by: Mapped[str | None] = mapped_column(String(40))
    superseded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    case: Mapped[Case] = relationship(back_populates="facts")


class ExtractionRun(Base):
    """One attempt to extract facts for a case: who ran it, what it cost, how it ended."""

    __tablename__ = "extraction_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))  # ok, failed, timed_out
    error: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[int] = mapped_column(Integer, default=0)
    dropped: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Summary(Base):
    """A drafted reviewer summary. Each sentence lists the fact IDs it came from."""

    __tablename__ = "summaries"
    __table_args__ = (
        CheckConstraint("review_status IN ('pending', 'accepted', 'edited')", name="summary_review_status_is_known"),
        CheckConstraint("review_status <> 'edited' OR edited_text IS NOT NULL", name="edited_summary_has_text"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    sentences: Mapped[list[dict]] = mapped_column(JSONB)
    method: Mapped[str] = mapped_column(String(20))
    review_status: Mapped[str] = mapped_column(String(10), default="pending")
    edited_text: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(40))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    """Append-only history. A trigger (below) refuses UPDATE and DELETE."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    event: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(40))
    actor_role: Mapped[str] = mapped_column(String(30))
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str | None] = mapped_column(String(20))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    trace_id: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# SQLAlchemy passes DDL strings through "%" formatting, so this SQL avoids "%".
APPEND_ONLY = DDL(
    """
    CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION USING MESSAGE = 'audit_events is append-only: ' || TG_OP || ' is not allowed';
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER audit_events_append_only
      BEFORE UPDATE OR DELETE ON audit_events
      FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();
    """
)
event.listen(AuditEvent.__table__, "after_create", APPEND_ONLY)
