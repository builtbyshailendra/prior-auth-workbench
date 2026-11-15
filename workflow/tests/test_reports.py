"""Step 14: reports. AS-14: the CMS metrics match a hand calculation on a fixed set of cases."""
from datetime import UTC, datetime, timedelta

from app import catalogue
from app.clocks import clock
from app.intake import receive
from app.lifecycle import take
from app.reports import cms_metrics, operations
from app.schemas import IntakeRequest
from tests.conftest import START
from tests.helpers import payload

EXPLANATION = "Six weeks of therapy are documented but no examination findings support imaging."


def decide(session, member, priority, hours_to_decision, outcome):
    """Receive a request at START, then decide it hours_to_decision later."""
    clock.set(START)
    case = receive(session, IntakeRequest(**payload(member_id=member, priority=priority)), catalogue=catalogue.load(),
                   actor="test", role="connector", trace_id="t").case
    clock.set(START + timedelta(hours=hours_to_decision))
    take(session, case, "start_review", user="nina", role="nurse_reviewer", trace_id="t")
    if outcome == "approved":
        take(session, case, "approve", user="nina", role="nurse_reviewer", trace_id="t")
    else:
        take(session, case, "escalate", user="nina", role="nurse_reviewer", trace_id="t", note="Please review")
        take(session, case, "deny", user="dr.lee", role="medical_director", trace_id="t",
             reason_code="documentation_does_not_support", note=EXPLANATION)
    session.commit()


def test_as14_cms_metrics_match_a_hand_calculation(session):
    # Standard: 10 h approved, 20 h approved, 60 h denied. Expedited: 4 h approved, 8 h denied.
    decide(session, "SYN-M0001", "standard", 10, "approved")
    decide(session, "SYN-M0002", "standard", 20, "approved")
    decide(session, "SYN-M0003", "standard", 60, "denied")
    decide(session, "SYN-M0004", "expedited", 4, "approved")
    decide(session, "SYN-M0005", "expedited", 8, "denied")
    report = cms_metrics(session, catalogue.load(), datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC))
    assert report["decisions"] == 5
    assert report["percent_approved"] == 60.0  # 3 of 5
    assert report["percent_denied"] == 40.0
    assert report["percent_approved_after_appeal"] == "not tracked: appeals are outside the pilot"
    assert report["decision_time_standard"] == {"count": 3, "average_hours": 30.0, "median_hours": 20.0}
    assert report["decision_time_expedited"] == {"count": 2, "average_hours": 6.0, "median_hours": 6.0}
    assert report["services_requiring_authorization"] == [
        "72148 Lumbar spine MRI", "95810 Sleep study in a sleep lab", "97110 Physical therapy beyond the plan's visit limit"]


def test_decisions_outside_the_year_are_left_out(session):
    decide(session, "SYN-M0001", "standard", 10, "approved")
    report = cms_metrics(session, catalogue.load(), datetime(2027, 1, 1, tzinfo=UTC), datetime(2028, 1, 1, tzinfo=UTC))
    assert report["decisions"] == 0 and report["percent_approved"] is None


def test_operations_report_counts_rework_and_speed(session):
    cat = catalogue.load()
    receive(session, IntakeRequest(**payload(member_id="SYN-M0001")), catalogue=cat, actor="t", role="connector", trace_id="t")
    receive(session, IntakeRequest(**payload(member_id="SYN-M0002", documents=[])), catalogue=cat, actor="t", role="connector",
            trace_id="t")
    receive(session, IntakeRequest(**payload(member_id="SYN-M0003", service_code="99213", documents=[])), catalogue=cat,
            actor="t", role="connector", trace_id="t")
    report = operations(session)
    assert report["cases_by_state"] == {"ready_for_review": 1, "pended": 1, "closed_no_auth": 1}
    assert report["rfi_rate_percent"] == 50.0  # 1 of the 2 that needed authorization
    assert report["intake_to_nurse_queue_seconds"]["cases"] == 1
    assert report["open_cases_by_risk"] == {"on_track": 2}


def test_reports_are_for_medical_directors_and_admins(as_user):
    assert as_user("admin").get("/api/reports/cms?year=2026").status_code == 200
    assert as_user("dr.lee").get("/api/reports/operations").status_code == 200
    assert as_user("nina").get("/api/reports/operations").status_code == 403
