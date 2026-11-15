"""Decision deadlines, modelled on CMS-0057-F: 72 hours expedited, 7 calendar days standard.

The clock starts at receipt and keeps running while a case waits for documents.
Whether a request for information may pause it depends on the plan's own policies
and contracts; that's an open question in the discovery pack, so the safe default
is a clock that never pauses.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

DEADLINE = {"expedited": timedelta(hours=72), "standard": timedelta(days=7)}
# A case is at risk when less than this is left.
AT_RISK = {"expedited": timedelta(hours=12), "standard": timedelta(hours=24)}


class Clock:
    """Current time, replaceable in tests."""

    def __init__(self) -> None:
        self._fixed: datetime | None = None

    def now(self) -> datetime:
        return self._fixed or datetime.now(UTC)

    def set(self, moment: datetime | None) -> None:
        self._fixed = moment


clock = Clock()


def due_at(priority: str, received_at: datetime) -> datetime:
    return received_at + DEADLINE[priority]


def risk(priority: str, due: datetime, now: datetime) -> str:
    left = due - now
    if left <= timedelta(0):
        return "overdue"
    if left <= AT_RISK[priority]:
        return "at_risk"
    return "on_track"


def hours_left(due: datetime, now: datetime) -> float:
    return round((due - now).total_seconds() / 3600, 1)
