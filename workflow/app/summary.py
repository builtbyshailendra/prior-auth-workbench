"""The reviewer summary: a few sentences built from the checked facts.

Each sentence comes from exactly one fact (or from the documents checklist), and carries
that fact's ID, so a reviewer can click from any sentence to its source. The summary is
built by template, not written by a model: the facts are already structured, and a
model rewriting them would add the risk of saying something the facts don't say,
without adding information. See docs/decisions/0004-summary-and-review.md.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.catalogue import Catalogue
from app.extraction.fields import FIELDS
from app.models import Case, Fact, Summary


def _sentence(fact: Fact) -> str | None:
    spec = FIELDS.get(fact.field)
    if spec is None:
        return None
    source = "entered by the reviewer" if fact.method == "manual" else "quoted from the documents"
    if fact.status == "dropped":
        return f"{spec.label}: an extracted answer couldn't be verified, so it needs checking by hand."
    if fact.value is None:
        return f"{spec.label}: not documented."
    if spec.kind == "boolean":
        value = "yes" if fact.value else "no"
    else:
        value = f"{fact.value} weeks" if fact.field.endswith("_weeks") else str(fact.value)
    return f"{spec.label}: {value} ({source})."


def draft(session: Session, case: Case, catalogue: Catalogue, *, trace_id: str) -> Summary:
    """Write a fresh summary from the case's current facts. Older summaries are kept, marked superseded."""
    for old in session.scalars(select(Summary).where(Summary.case_id == case.id, Summary.superseded.is_(False))):
        old.superseded = True
    facts = [f for f in case.facts if not f.superseded]
    service = catalogue.service(case.service_code)
    sentences = [{"text": f"{service.name if service else case.service_code} for {case.member_id}, "
                          f"{'expedited' if case.priority == 'expedited' else 'standard'} request. "
                          f"All required documents received.", "fact_ids": []}]
    for fact in facts:
        text = _sentence(fact)
        if text:
            sentences.append({"text": text, "fact_ids": [fact.id]})
    unverified = sum(f.status == "dropped" for f in facts)
    if unverified:
        sentences.append({"text": f"{unverified} answer(s) couldn't be verified; check the documents before deciding.",
                          "fact_ids": [f.id for f in facts if f.status == "dropped"]})
    summary = Summary(case_id=case.id, text=" ".join(s["text"] for s in sentences), sentences=sentences,
                      method="template", review_status="pending")
    session.add(summary)
    session.flush()
    audit.record(session, case, "summary_drafted", actor="workflow", role="system", trace_id=trace_id,
                 detail={"sentences": len(sentences), "unverified": unverified})
    return summary


def current(session: Session, case: Case) -> Summary | None:
    return session.scalars(
        select(Summary).where(Summary.case_id == case.id, Summary.superseded.is_(False)).order_by(Summary.id.desc())
    ).first()
