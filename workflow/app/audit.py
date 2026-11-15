"""Writing to the append-only audit trail. Details carry IDs and codes, never note text or names."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditEvent, Case


def record(
    session: Session,
    case: Case,
    event: str,
    *,
    actor: str,
    role: str,
    trace_id: str,
    from_state: str | None = None,
    to_state: str | None = None,
    detail: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            case_id=case.id,
            event=event,
            actor=actor,
            actor_role=role,
            from_state=from_state,
            to_state=to_state,
            detail=detail or {},
            trace_id=trace_id,
        )
    )


def move(session: Session, case: Case, to_state: str, event: str, *, actor: str, role: str, trace_id: str, detail: dict | None = None) -> None:
    """Change a case's state and record it in the same transaction."""
    from_state = case.state
    case.state = to_state
    record(session, case, event, actor=actor, role=role, trace_id=trace_id, from_state=from_state, to_state=to_state, detail=detail)
