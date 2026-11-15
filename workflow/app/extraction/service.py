"""The workflow service's side of extraction.

The extraction worker is a separate process holding only the extractor token. It claims
cases waiting for extraction, runs the model, and sends back raw answers. This module
checks those answers against the documents itself, stores the facts, and moves the case
to the nurse queue. If the worker fails, or never answers, the case goes to manual entry:
intake never waits on the AI.

EXTRACTION_MODE=off (default)  complete cases go straight to review with facts marked for manual entry
EXTRACTION_MODE=worker         complete cases wait for the worker, up to EXTRACTION_TIMEOUT_MINUTES (default 10)
"""
from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit, summary
from app.catalogue import Catalogue
from app.clocks import clock
from app.extraction.fields import FIELDS
from app.extraction.verify import RawFact, check
from app.lifecycle import WrongState
from app.models import Case, ExtractionRun, Fact

LEASE = timedelta(minutes=5)


def mode() -> str:
    return os.environ.get("EXTRACTION_MODE", "off")


def timeout() -> timedelta:
    return timedelta(minutes=float(os.environ.get("EXTRACTION_TIMEOUT_MINUTES", "10")))


def _ready(session: Session, case: Case, trace_id: str, catalogue: Catalogue) -> None:
    case.ready_at = clock.now()
    audit.move(session, case, "ready_for_review", "ready_for_review", actor="workflow", role="system", trace_id=trace_id,
               detail={"extraction": case.extraction_status})
    if case.extraction_status != "not_applicable":
        session.flush()
        session.refresh(case)
        summary.draft(session, case, catalogue, trace_id=trace_id)


def complete_case(session: Session, case: Case, catalogue: Catalogue, trace_id: str) -> None:
    """Called by intake once a case has every document it needs."""
    service = catalogue.service(case.service_code)
    if service is None or not service.facts:
        case.extraction_status = "not_applicable"
        _ready(session, case, trace_id, catalogue)
    elif mode() == "worker":
        case.extraction_status = "pending"
        case.extraction_requested_at = clock.now()
        case.extraction_claimed_at = None
        audit.record(session, case, "awaiting_extraction", actor="workflow", role="system", trace_id=trace_id)
    else:
        case.extraction_status = "manual_needed"
        _ready(session, case, trace_id, catalogue)


def claim(session: Session, limit: int) -> list[Case]:
    """Cases waiting for extraction, earliest deadline first. Each is leased for 5 minutes."""
    now = clock.now()
    cases = session.scalars(
        select(Case)
        .where(Case.state == "received", Case.extraction_status == "pending",
               or_(Case.extraction_claimed_at.is_(None), Case.extraction_claimed_at < now - LEASE))
        .order_by(Case.due_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for case in cases:
        case.extraction_claimed_at = now
    session.commit()
    return cases


def job(case: Case, catalogue: Catalogue) -> dict:
    wanted = list(catalogue.service(case.service_code).facts)
    return {
        "case_id": case.id,
        "service_code": case.service_code,
        "wanted": wanted,
        "fields": [{"name": f, "kind": FIELDS[f].kind, "meaning": FIELDS[f].meaning} for f in wanted],
        "documents": [{"id": d.id, "doc_type": d.doc_type, "title": d.title, "text": d.text} for d in case.documents],
    }


def record_result(session: Session, case_id: int, result, catalogue: Catalogue, trace_id: str) -> Case | None:
    """Check the worker's answers, store the facts and send the case to review."""
    case = session.get(Case, case_id, with_for_update=True)
    if case is None:
        return None
    if case.state != "received" or case.extraction_status != "pending":
        raise WrongState("No extraction is waiting for this case")
    run = ExtractionRun(case_id=case.id, provider=result.provider, model=result.model, status=result.status,
                        error=result.error[:500], input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd, duration_ms=result.duration_ms)
    if result.status == "ok":
        documents = list(case.documents)
        wanted = list(catalogue.service(case.service_code).facts)
        checked = check([RawFact(f.field, f.value, f.quote) for f in result.facts], [d.text for d in documents], wanted)
        method = "ai" if result.provider == "claude" else "rules"
        for c in checked:
            session.add(Fact(
                case=case, field=c.field, value=c.value,
                quote=c.quote if c.status != "not_documented" else None,
                document_id=documents[c.document_index].id if c.document_index is not None else None,
                method=method, status=c.status, note=c.reason,
            ))
        run.verified = sum(c.status == "verified" for c in checked)
        run.dropped = sum(c.status == "dropped" for c in checked)
        case.extraction_status = "complete"
        audit.record(session, case, "facts_extracted", actor="extraction-worker", role="extractor", trace_id=trace_id,
                     detail={"provider": result.provider, "model": result.model, "verified": run.verified,
                             "dropped": run.dropped,
                             "not_documented": sum(c.status == "not_documented" for c in checked)})
    else:
        case.extraction_status = "manual_needed"
        audit.record(session, case, "extraction_failed", actor="extraction-worker", role="extractor", trace_id=trace_id,
                     detail={"provider": result.provider, "model": result.model})
    session.add(run)
    _ready(session, case, trace_id, catalogue)
    session.commit()
    return case


def sweep(session: Session, catalogue: Catalogue, trace_id: str = "extraction-sweep") -> int:
    """Send cases whose extraction never came back to manual entry. Returns how many."""
    cutoff = clock.now() - timeout()
    stale = session.scalars(
        select(Case)
        .where(Case.state == "received", Case.extraction_status == "pending", Case.extraction_requested_at < cutoff)
        .with_for_update(skip_locked=True)
    ).all()
    for case in stale:
        case.extraction_status = "manual_needed"
        session.add(ExtractionRun(case_id=case.id, provider="none", model="", status="timed_out",
                                  error=f"No answer within {timeout()}"))
        audit.record(session, case, "extraction_timed_out", actor="workflow", role="system", trace_id=trace_id)
        _ready(session, case, trace_id, catalogue)
    session.commit()
    return len(stale)
