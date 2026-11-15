"""What a reviewer does with the gathered facts: enter missing ones, correct wrong ones,
and accept or edit the drafted summary. Every change is attributed and audited, and the
AI's original answer is kept (marked superseded), so you can later count how often
reviewers had to correct it.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import audit, summary
from app.catalogue import Catalogue
from app.clocks import clock
from app.extraction.verify import parse_value
from app.lifecycle import Invalid, NotAllowed, WrongState
from app.models import Case, Fact


def check_reviewer(case: Case, role: str, username: str) -> None:
    if role == "nurse_reviewer" and case.state == "in_nurse_review" and case.assigned_to == username:
        return
    if role == "medical_director" and case.state == "escalated":
        return
    if role in ("nurse_reviewer", "medical_director"):
        raise WrongState("Facts and the summary can be changed while you're reviewing the case.")
    raise NotAllowed("Only the reviewer of a case can change its facts or summary.")


def enter_fact(session: Session, case: Case, *, field: str, value: str | None, note: str, user: str, role: str,
               trace_id: str, catalogue: Catalogue) -> Fact:
    check_reviewer(case, role, user)
    service = catalogue.service(case.service_code)
    if service is None or field not in service.facts:
        raise Invalid(f"{field} isn't a checklist fact for this service.")
    ok, parsed = parse_value(field, value)
    if not ok:
        raise Invalid(f"{value!r} isn't a valid answer for {field}.")
    if len(note.strip()) < 3:
        raise Invalid("Say where in the documents this comes from.")
    replaced = [f for f in case.facts if f.field == field and not f.superseded]
    for old in replaced:
        old.superseded = True
    fact = Fact(case=case, field=field, value=parsed, quote=None, document_id=None, method="manual", status="entered",
                note=note.strip(), entered_by=user)
    session.add(fact)
    session.flush()
    audit.record(session, case, "fact_entered", actor=user, role=role, trace_id=trace_id,
                 detail={"field": field, "replaced": [f"{f.method}:{f.status}" for f in replaced]})
    session.refresh(case)
    summary.draft(session, case, catalogue, trace_id=trace_id)
    return fact


def review_summary(session: Session, case: Case, *, accepted: bool, edited_text: str | None, user: str, role: str,
                   trace_id: str) -> None:
    check_reviewer(case, role, user)
    current = summary.current(session, case)
    if current is None:
        raise Invalid("There's no summary to review.")
    if current.review_status != "pending":
        raise WrongState("This summary has already been reviewed.")
    if not accepted and len((edited_text or "").strip()) < 10:
        raise Invalid("An edited summary needs at least a sentence.")
    current.review_status = "accepted" if accepted else "edited"
    current.edited_text = None if accepted else edited_text.strip()
    current.reviewed_by = user
    current.reviewed_at = clock.now()
    audit.record(session, case, "summary_reviewed", actor=user, role=role, trace_id=trace_id,
                 detail={"result": current.review_status})
