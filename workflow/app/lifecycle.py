"""Who may move a case from which state to which. People decide; nothing here is automatic.

The rules in one table, so they can be read (and argued about) in one place.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import audit
from app.clocks import clock
from app.models import Case

ROLE_NAMES = {
    "intake_coordinator": "an intake coordinator",
    "nurse_reviewer": "a nurse reviewer",
    "medical_director": "a medical director",
    "admin": "an admin",
    "connector": "a connector",
    "extractor": "the extraction service",
}

# Illustrative reason codes. A denial must carry one of these plus a written explanation.
REASON_CODES = {
    "documentation_does_not_support": "The documentation sent doesn't show the plan's criteria are met",
    "conservative_treatment_not_tried": "Conservative treatment hasn't been tried for long enough",
    "service_not_covered": "The service isn't a covered benefit under the member's plan",
    "more_appropriate_alternative": "A more appropriate service or setting is available",
}


@dataclass(frozen=True)
class Action:
    from_states: frozenset[str]
    roles: frozenset[str]
    to_state: str
    refusal: str  # said to anyone whose role can't take this action


ACTIONS = {
    "start_review": Action(frozenset({"ready_for_review"}), frozenset({"nurse_reviewer"}), "in_nurse_review",
                           "Only a nurse reviewer can pick up a case for review."),
    "approve": Action(frozenset({"in_nurse_review", "escalated"}), frozenset({"nurse_reviewer", "medical_director"}),
                      "approved", "Only a nurse reviewer or a medical director can approve a case."),
    "escalate": Action(frozenset({"in_nurse_review"}), frozenset({"nurse_reviewer"}), "escalated",
                       "Only a nurse reviewer can escalate a case to a medical director."),
    "deny": Action(frozenset({"escalated"}), frozenset({"medical_director"}), "denied",
                   "Only a medical director can deny a case. A nurse reviewer can escalate it instead."),
    "withdraw": Action(frozenset({"received", "pended", "ready_for_review"}), frozenset({"intake_coordinator"}),
                       "withdrawn", "Only an intake coordinator can withdraw a request."),
}

# Which cases each role sees (FR-15). Admins manage users, not cases.
VISIBLE_STATES = {
    "intake_coordinator": {"received", "pended", "ready_for_review", "closed_no_auth", "closed_ineligible", "withdrawn"},
    "nurse_reviewer": {"ready_for_review", "in_nurse_review", "escalated", "approved", "denied"},
    "medical_director": {"escalated", "approved", "denied"},
}


class NotAllowed(Exception):
    """The person's role can't do this (HTTP 403)."""


class WrongState(Exception):
    """The case isn't in a state where this can happen (HTTP 409)."""


class Invalid(Exception):
    """Something required is missing, like a denial reason (HTTP 422)."""


def can_view(case: Case, role: str) -> bool:
    return case.state in VISIBLE_STATES.get(role, set())


def take(
    session: Session,
    case: Case,
    action_name: str,
    *,
    user: str,
    role: str,
    trace_id: str,
    note: str = "",
    reason_code: str | None = None,
) -> Case:
    """Apply one action to a case that the caller has locked (SELECT ... FOR UPDATE)."""
    action = ACTIONS[action_name]
    if role not in action.roles:
        raise NotAllowed(action.refusal)
    if case.state not in action.from_states:
        state = case.state.replace("_", " ")
        raise WrongState(f"Can't {action_name.replace('_', ' ')} a case that is {state}.")

    if action_name == "approve":
        if role == "nurse_reviewer" and case.state != "in_nurse_review":
            raise WrongState("A nurse reviewer approves cases in their own review, not escalated ones.")
        if role == "medical_director" and case.state != "escalated":
            raise WrongState("A medical director decides escalated cases.")
    if role == "nurse_reviewer" and case.state == "in_nurse_review" and case.assigned_to != user:
        raise NotAllowed(f"This case is being reviewed by {case.assigned_to}.")
    if action_name == "escalate" and not note.strip():
        raise Invalid("Say why you're escalating, so the medical director knows what to look at.")
    if action_name == "withdraw" and not note.strip():
        raise Invalid("A withdrawal needs a reason.")
    if action_name == "deny":
        if reason_code not in REASON_CODES:
            raise Invalid(f"A denial needs a reason code, one of: {', '.join(REASON_CODES)}.")
        if len(note.strip()) < 20:
            raise Invalid("A denial needs a written explanation of at least 20 characters.")

    detail: dict = {}
    if action_name == "start_review":
        case.assigned_to = user
    if action_name in ("approve", "deny"):
        case.decided_by = user
        case.decided_at = clock.now()
    if action_name == "deny":
        case.decision_reason_code = reason_code
        case.decision_explanation = note.strip()
        detail["reason_code"] = reason_code
    if action_name == "escalate":
        case.escalation_note = note.strip()
    if action_name == "withdraw":
        case.closed_reason = note.strip()
    audit.move(session, case, action.to_state, action_name, actor=user, role=role, trace_id=trace_id, detail=detail)
    return case
