"""How cases look in API responses."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue import Catalogue
from app.clocks import clock, hours_left, risk
from app.intake import open_rfi
from app.lifecycle import REASON_CODES
from app.models import AuditEvent, Case

OPEN = {"received", "pended", "ready_for_review", "in_nurse_review", "escalated"}


def case_summary(case: Case, catalogue: Catalogue) -> dict:
    service = catalogue.service(case.service_code)
    now = clock.now()
    is_open = case.state in OPEN
    return {
        "id": case.id,
        "state": case.state,
        "priority": case.priority,
        "member": {"id": case.member_id, "name": case.member_name},
        "provider": {"npi": case.provider_npi, "name": case.provider_name},
        "service": {"code": case.service_code, "name": service.name if service else "Not in the catalogue"},
        "received_at": case.received_at.isoformat(),
        "due_at": case.due_at.isoformat(),
        "risk": risk(case.priority, case.due_at, now) if is_open else "closed",
        "hours_left": hours_left(case.due_at, now) if is_open else None,
        "rfi_count": case.rfi_count,
        "extraction_status": case.extraction_status,
        "assigned_to": case.assigned_to,
    }


def case_detail(session: Session, case: Case, catalogue: Catalogue) -> dict:
    rfi = open_rfi(case)
    events = session.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.id)).all()
    return {
        **case_summary(case, catalogue),
        "diagnosis_codes": case.diagnosis_codes,
        "service_date_start": case.service_date_start.isoformat(),
        "service_date_end": case.service_date_end.isoformat() if case.service_date_end else None,
        "catalogue_version": case.catalogue_version,
        "missing": rfi.items if rfi else [],
        "closed_reason": case.closed_reason,
        "escalation_note": case.escalation_note,
        "decision": None if not case.decided_by else {
            "by": case.decided_by,
            "at": case.decided_at.isoformat() if case.decided_at else None,
            "reason_code": case.decision_reason_code,
            "reason": REASON_CODES.get(case.decision_reason_code or ""),
            "explanation": case.decision_explanation,
        },
        "documents": [
            {"id": d.id, "doc_type": d.doc_type, "title": d.title, "received_at": d.received_at.isoformat()}
            for d in case.documents
        ],
        "submissions": [{"source": s.source, "source_id": s.source_id} for s in case.submissions],
        "rfis": [
            {"items": r.items, "created_at": r.created_at.isoformat(),
             "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None}
            for r in case.rfis
        ],
        "history": [
            {"event": e.event, "actor": e.actor, "role": e.actor_role, "from": e.from_state, "to": e.to_state,
             "detail": e.detail, "trace_id": e.trace_id, "at": e.at.isoformat()}
            for e in events
        ],
    }
