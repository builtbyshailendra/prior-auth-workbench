"""Reports: the CMS-style yearly metrics, and the operational measures for the pilot.

Aggregates only: no member names, no notes, no case contents.
"""
from __future__ import annotations

from datetime import datetime
from statistics import mean, median

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.catalogue import Catalogue
from app.clocks import clock, risk
from app.models import OPEN_STATES, AuditEvent, Case, ExtractionRun, Fact, Summary


def _hours(seconds: float) -> float:
    return round(seconds / 3600, 1)


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "average_hours": None, "median_hours": None}
    return {"count": len(values), "average_hours": _hours(mean(values)), "median_hours": _hours(median(values))}


def cms_metrics(session: Session, catalogue: Catalogue, start: datetime, end: datetime) -> dict:
    """The prior-authorization metrics CMS-0057-F asks impacted payers to publish each year,
    for decisions made in [start, end). Appeals are outside the pilot, so that one is reported as not tracked."""
    decided = session.execute(
        select(Case.state, Case.priority, Case.received_at, Case.decided_at)
        .where(Case.state.in_(("approved", "denied")), Case.decided_at >= start, Case.decided_at < end)
    ).all()
    total = len(decided)
    approved = sum(1 for d in decided if d.state == "approved")
    times = {
        p: [(d.decided_at - d.received_at).total_seconds() for d in decided if d.priority == p]
        for p in ("standard", "expedited")
    }
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "services_requiring_authorization": sorted(
            f"{s.code} {s.name}" for s in catalogue.services.values() if s.auth_required),
        "decisions": total,
        "percent_approved": round(100 * approved / total, 1) if total else None,
        "percent_denied": round(100 * (total - approved) / total, 1) if total else None,
        "percent_approved_after_appeal": "not tracked: appeals are outside the pilot",
        "decision_time_standard": _stats(times["standard"]),
        "decision_time_expedited": _stats(times["expedited"]),
    }


def operations(session: Session) -> dict:
    """What the pilot measures: speed to a nurse, rework, AI outcomes and reviewer corrections."""
    now = clock.now()
    states = dict(session.execute(select(Case.state, func.count()).group_by(Case.state)).all())
    needed_auth = session.scalar(select(func.count()).select_from(Case).where(
        Case.state.not_in(("closed_no_auth", "closed_ineligible")))) or 0
    pended_once = session.scalar(select(func.count()).select_from(Case).where(Case.rfi_count > 0)) or 0

    # System time from intake to the nurse queue, from the audit trail's server clock,
    # for cases that never waited on the provider (so it measures the software, not the provider).
    first_received = (select(AuditEvent.case_id, func.min(AuditEvent.at).label("at"))
                      .where(AuditEvent.event == "received").group_by(AuditEvent.case_id).subquery())
    first_ready = (select(AuditEvent.case_id, func.min(AuditEvent.at).label("at"))
                   .where(AuditEvent.event == "ready_for_review").group_by(AuditEvent.case_id).subquery())
    rows = session.execute(
        select(first_received.c.at, first_ready.c.at)
        .join(first_ready, first_ready.c.case_id == first_received.c.case_id)
        .join(Case, and_(Case.id == first_received.c.case_id, Case.rfi_count == 0))
    ).all()
    to_ready = sorted((ready - received).total_seconds() for received, ready in rows)

    runs = dict(((p, s), n) for p, s, n in session.execute(
        select(ExtractionRun.provider, ExtractionRun.status, func.count())
        .group_by(ExtractionRun.provider, ExtractionRun.status)).all())
    current = dict(((m, s), n) for m, s, n in session.execute(
        select(Fact.method, Fact.status, func.count()).where(Fact.superseded.is_(False))
        .group_by(Fact.method, Fact.status)).all())
    corrected = session.scalar(select(func.count()).select_from(Fact).where(
        Fact.superseded.is_(True), Fact.method.in_(("ai", "rules")), Fact.status == "verified")) or 0
    filled_in = session.scalar(select(func.count()).select_from(Fact).where(
        Fact.superseded.is_(True), Fact.method.in_(("ai", "rules")), Fact.status.in_(("dropped", "not_documented")))) or 0
    reviews = dict(session.execute(select(Summary.review_status, func.count())
                                   .where(Summary.superseded.is_(False)).group_by(Summary.review_status)).all())
    open_risk: dict[str, int] = {}
    for priority, due in session.execute(select(Case.priority, Case.due_at).where(Case.state.in_(OPEN_STATES))):
        level = risk(priority, due, now)
        open_risk[level] = open_risk.get(level, 0) + 1
    cost = session.scalar(select(func.coalesce(func.sum(ExtractionRun.cost_usd), 0.0))) or 0.0
    reviewed = reviews.get("accepted", 0) + reviews.get("edited", 0)
    return {
        "cases_by_state": states,
        "rfi_rate_percent": round(100 * pended_once / needed_auth, 1) if needed_auth else None,
        "intake_to_nurse_queue_seconds": {
            "cases": len(to_ready),
            "median": round(median(to_ready), 2) if to_ready else None,
            "p95": round(to_ready[int(0.95 * (len(to_ready) - 1))], 2) if to_ready else None,
            "max": round(to_ready[-1], 2) if to_ready else None,
        },
        "extraction_runs": {f"{p}:{s}": n for (p, s), n in runs.items()},
        "current_facts": {f"{m}:{s}": n for (m, s), n in current.items()},
        "verified_facts_corrected_by_reviewers": corrected,
        "unverified_facts_filled_in_by_reviewers": filled_in,
        "summaries": {**reviews, "accepted_unchanged_percent": round(100 * reviews.get("accepted", 0) / reviewed, 1)
                      if reviewed else None},
        "open_cases_by_risk": open_risk,
        "extraction_cost_usd": round(float(cost), 4),
    }
