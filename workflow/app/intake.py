"""Intake: from one incoming request to a case in the right state.

received -> closed_ineligible   member not covered on the service date
         -> closed_no_auth      service doesn't need authorization
         -> pended              documents missing (one request listing all of them)
         -> ready_for_review    complete; facts gathered (by AI from Step 10, or marked for manual entry)
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit
from app.catalogue import Catalogue
from app.clocks import clock, due_at
from app.models import OPEN_STATES, Case, Coverage, Document, Rfi, Submission
from app.schemas import DocumentIn, IntakeRequest
from app.validation import CoveragePeriod, Problem, check_request, covered_on

# Called once a case is complete. Step 3 marks facts for manual entry; Step 10 runs extraction here.
OnComplete = Callable[[Session, Case, Catalogue, str], None]


class IntakeRejected(Exception):
    """The request fails format checks. Nothing is stored; the sender keeps it and can fix and resend."""

    def __init__(self, problems: list[Problem]):
        super().__init__("; ".join(p.message for p in problems))
        self.problems = problems


class CaseClosed(Exception):
    """Documents sent for a case that's no longer open."""


@dataclass
class IntakeResult:
    case: Case
    outcome: str  # created | linked | replayed


def business_key(member_id: str, npi: str, service_code: str, start) -> str:
    return hashlib.sha256(f"{member_id}|{npi}|{service_code}|{start.isoformat()}".encode()).hexdigest()[:32]


def open_rfi(case: Case) -> Rfi | None:
    return next((r for r in reversed(case.rfis) if r.resolved_at is None), None)


def mark_ready_for_manual_facts(session: Session, case: Case, catalogue: Catalogue, trace_id: str) -> None:
    """Default completion step: no AI yet, so a person enters the facts."""
    service = catalogue.service(case.service_code)
    case.extraction_status = "manual_needed" if service and service.facts else "not_applicable"
    case.ready_at = clock.now()
    audit.move(session, case, "ready_for_review", "ready_for_review", actor="workflow", role="system", trace_id=trace_id,
               detail={"extraction": case.extraction_status})


def receive(
    session: Session,
    request: IntakeRequest,
    *,
    catalogue: Catalogue,
    actor: str,
    role: str,
    trace_id: str,
    on_complete: OnComplete = mark_ready_for_manual_facts,
) -> IntakeResult:
    replay = session.scalar(
        select(Submission).where(Submission.source == request.source, Submission.source_id == request.source_id)
    )
    if replay is not None:
        return IntakeResult(replay.case, "replayed")

    service = request.service
    problems = check_request(
        member_id=request.member.id,
        provider_npi=request.provider.npi,
        service_code=service.code,
        diagnosis_codes=service.diagnosis_codes,
        service_date_start=service.date_start,
        service_date_end=service.date_end,
    )
    if problems:
        raise IntakeRejected(problems)

    key = business_key(request.member.id, request.provider.npi, service.code, service.date_start)
    # Requests for the same member, provider, service and date take turns, so a fax and an
    # X12 278 arriving together can't both open a case. Released when the transaction ends.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
    existing = session.scalar(
        select(Case).where(Case.business_key == key, Case.state.in_(OPEN_STATES)).with_for_update()
    )
    if existing is not None:
        session.add(Submission(case=existing, source=request.source, source_id=request.source_id, trace_id=trace_id))
        audit.record(session, existing, "duplicate_linked", actor=actor, role=role, trace_id=trace_id,
                     detail={"source": request.source})
        if request.documents:
            _add_documents(session, existing, request.documents, catalogue, actor, role, trace_id, on_complete)
        session.commit()
        return IntakeResult(existing, "linked")

    received_at = request.received_at or clock.now()
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)
    case = Case(
        business_key=key,
        member_id=request.member.id,
        member_name=request.member.name,
        provider_npi=request.provider.npi,
        provider_name=request.provider.name,
        service_code=service.code,
        diagnosis_codes=service.diagnosis_codes,
        service_date_start=service.date_start,
        service_date_end=service.date_end,
        priority=request.priority,
        state="received",
        received_at=received_at,
        due_at=due_at(request.priority, received_at),
        catalogue_version=catalogue.version,
        rfi_count=0,
        extraction_status="not_started",
    )
    session.add(case)
    session.flush()
    session.add(Submission(case=case, source=request.source, source_id=request.source_id, trace_id=trace_id))
    audit.record(session, case, "received", actor=actor, role=role, trace_id=trace_id, to_state="received",
                 detail={"source": request.source, "priority": request.priority, "service_code": service.code,
                         "catalogue_version": catalogue.version})
    for doc in request.documents:
        session.add(Document(case=case, doc_type=doc.doc_type, title=doc.title, text=doc.text))
    session.flush()
    _route(session, case, catalogue, actor, role, trace_id, on_complete)
    session.commit()
    return IntakeResult(case, "created")


def add_documents(
    session: Session,
    case_id: int,
    documents: list[DocumentIn],
    *,
    catalogue: Catalogue,
    actor: str,
    role: str,
    trace_id: str,
    on_complete: OnComplete = mark_ready_for_manual_facts,
) -> Case | None:
    case = session.get(Case, case_id, with_for_update=True)
    if case is None:
        return None
    if case.state not in OPEN_STATES:
        raise CaseClosed(f"Case {case.id} is {case.state.replace('_', ' ')} and can't take new documents")
    _add_documents(session, case, documents, catalogue, actor, role, trace_id, on_complete)
    session.commit()
    return case


def _add_documents(session, case, documents, catalogue, actor, role, trace_id, on_complete) -> None:
    for doc in documents:
        session.add(Document(case=case, doc_type=doc.doc_type, title=doc.title, text=doc.text))
    session.flush()
    session.refresh(case)
    received_types = {d.doc_type for d in case.documents}
    missing = catalogue.missing_documents(case.service_code, received_types)
    audit.record(session, case, "documents_received", actor=actor, role=role, trace_id=trace_id,
                 detail={"types": sorted({d.doc_type for d in documents}), "still_missing": [m.type for m in missing]})
    if case.state != "pended":
        return
    rfi = open_rfi(case)
    if missing:
        if rfi is not None:
            rfi.items = [{"type": m.type, "label": m.label} for m in missing]
        return
    if rfi is not None:
        rfi.resolved_at = clock.now()
    audit.move(session, case, "received", "rechecked", actor="workflow", role="system", trace_id=trace_id)
    _route(session, case, catalogue, actor, role, trace_id, on_complete)


def _coverage(session: Session, member_id: str) -> list[CoveragePeriod]:
    rows = session.scalars(select(Coverage).where(Coverage.member_id == member_id)).all()
    return [CoveragePeriod(r.start, r.end) for r in rows]


def _route(session, case: Case, catalogue: Catalogue, actor, role, trace_id, on_complete: OnComplete) -> None:
    if not covered_on(_coverage(session, case.member_id), case.service_date_start):
        case.closed_reason = f"Member {case.member_id} isn't covered on {case.service_date_start.isoformat()}"
        audit.move(session, case, "closed_ineligible", "closed_ineligible", actor="workflow", role="system",
                   trace_id=trace_id)
        return
    if not catalogue.needs_authorization(case.service_code):
        case.closed_reason = (
            f"Service {case.service_code} doesn't need authorization (catalogue {catalogue.version})"
        )
        audit.move(session, case, "closed_no_auth", "closed_no_auth", actor="workflow", role="system",
                   trace_id=trace_id, detail={"catalogue_version": catalogue.version})
        return
    missing = catalogue.missing_documents(case.service_code, {d.doc_type for d in case.documents})
    if missing:
        items = [{"type": m.type, "label": m.label} for m in missing]
        session.add(Rfi(case=case, items=items, created_at=clock.now()))
        case.rfi_count += 1
        audit.move(session, case, "pended", "pended", actor="workflow", role="system", trace_id=trace_id,
                   detail={"missing": [m.type for m in missing]})
        return
    on_complete(session, case, catalogue, trace_id)


def now_utc() -> datetime:
    return clock.now()
