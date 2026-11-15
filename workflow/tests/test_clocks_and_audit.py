"""Step 3: deadline clocks (AS-03) and the append-only audit trail (AS-12)."""
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import catalogue
from app.clocks import clock, risk
from app.intake import receive
from app.lifecycle import take
from app.models import AuditEvent, Case
from app.schemas import IntakeRequest
from tests.conftest import START
from tests.helpers import payload


def test_as03_an_expedited_request_runs_on_a_72_hour_clock(client):
    case = client.post("/api/intake", json=payload(priority="expedited")).json()["case"]
    assert case["hours_left"] == 72.0
    clock.set(START + timedelta(hours=59))
    assert client.get(f"/api/cases/{case['id']}").json()["risk"] == "on_track"
    clock.set(START + timedelta(hours=60))
    at_risk = client.get(f"/api/cases/{case['id']}").json()
    assert (at_risk["risk"], at_risk["hours_left"]) == ("at_risk", 12.0)
    clock.set(START + timedelta(hours=72))
    assert client.get(f"/api/cases/{case['id']}").json()["risk"] == "overdue"


def test_standard_requests_turn_at_risk_on_their_last_day():
    due = START + timedelta(days=7)
    assert risk("standard", due, START + timedelta(days=6)) == "at_risk"
    assert risk("standard", due, START + timedelta(days=5, hours=23)) == "on_track"


def test_a_pended_case_keeps_its_clock_running(client):
    case = client.post("/api/intake", json=payload(documents=[])).json()["case"]
    clock.set(START + timedelta(days=6, hours=1))
    assert client.get(f"/api/cases/{case['id']}").json()["risk"] == "at_risk"


def test_closed_cases_have_no_risk(client):
    case = client.post("/api/intake", json=payload(service_code="99213", documents=[])).json()["case"]
    assert (case["risk"], case["hours_left"]) == ("closed", None)


def ready_case(session) -> Case:
    result = receive(session, IntakeRequest(**payload()), catalogue=catalogue.load(), actor="fax-connector",
                     role="connector", trace_id="trace-1")
    return result.case


def test_as12_the_audit_trail_is_complete_and_in_order(session):
    case = ready_case(session)
    take(session, case, "start_review", user="nina", role="nurse_reviewer", trace_id="trace-2")
    take(session, case, "approve", user="nina", role="nurse_reviewer", trace_id="trace-3")
    session.commit()
    events = session.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.id)).all()
    assert [(e.event, e.actor, e.from_state, e.to_state, e.trace_id) for e in events] == [
        ("received", "fax-connector", None, "received", "trace-1"),
        ("ready_for_review", "workflow", "received", "ready_for_review", "trace-1"),
        ("start_review", "nina", "ready_for_review", "in_nurse_review", "trace-2"),
        ("approve", "nina", "in_nurse_review", "approved", "trace-3"),
    ]


@pytest.mark.parametrize("statement", ["UPDATE audit_events SET actor = 'someone else'", "DELETE FROM audit_events"])
def test_as12_audit_rows_cant_be_edited_or_deleted(session, statement):
    ready_case(session)
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text(statement))
    session.rollback()


def test_audit_details_never_carry_note_text(session):
    case = ready_case(session)
    session.commit()
    for event in session.scalars(select(AuditEvent).where(AuditEvent.case_id == case.id)):
        assert "physical therapy" not in str(event.detail).lower()


def test_the_database_refuses_a_denial_without_a_reason(session):
    case = ready_case(session)
    case.state = "denied"
    case.decided_by = "someone"
    case.decided_at = START
    with pytest.raises(IntegrityError, match="denial_has_reason"):
        session.commit()
    session.rollback()


def test_the_database_refuses_two_open_cases_for_the_same_request(session):
    first = ready_case(session)
    session.add(Case(**{c: getattr(first, c) for c in (
        "business_key", "member_id", "provider_npi", "service_code", "diagnosis_codes", "service_date_start",
        "priority", "received_at", "due_at", "catalogue_version")}, state="received", rfi_count=0,
        extraction_status="not_started"))
    with pytest.raises(IntegrityError, match="one_open_case_per_request"):
        session.commit()
    session.rollback()
