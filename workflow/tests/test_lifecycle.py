"""Step 3: who may move a case where. Checked at the service level; Step 4 adds sign-in on top."""
import pytest

from app import catalogue
from app.intake import receive
from app.lifecycle import Invalid, NotAllowed, WrongState, take
from app.schemas import IntakeRequest
from tests.helpers import payload

EXPLANATION = "Six weeks of therapy are documented but no examination findings support imaging."


def new_case(session, **kwargs):
    return receive(session, IntakeRequest(**payload(**kwargs)), catalogue=catalogue.load(), actor="test",
                   role="connector", trace_id="t").case


def in_review(session, nurse="nina"):
    case = new_case(session)
    return take(session, case, "start_review", user=nurse, role="nurse_reviewer", trace_id="t")


def test_a_nurse_picks_up_and_approves(session):
    case = in_review(session)
    take(session, case, "approve", user="nina", role="nurse_reviewer", trace_id="t")
    assert (case.state, case.decided_by, case.assigned_to) == ("approved", "nina", "nina")
    assert case.decided_at is not None


def test_as10_a_nurse_cant_deny(session):
    case = in_review(session)
    with pytest.raises(NotAllowed, match="Only a medical director can deny a case"):
        take(session, case, "deny", user="nina", role="nurse_reviewer", trace_id="t",
             reason_code="service_not_covered", note=EXPLANATION)
    assert case.state == "in_nurse_review"


def test_a_nurse_cant_decide_a_case_another_nurse_is_reviewing(session):
    case = in_review(session, nurse="nina")
    with pytest.raises(NotAllowed, match="being reviewed by nina"):
        take(session, case, "approve", user="omar", role="nurse_reviewer", trace_id="t")


def test_escalation_needs_a_note(session):
    case = in_review(session)
    with pytest.raises(Invalid, match="Say why"):
        take(session, case, "escalate", user="nina", role="nurse_reviewer", trace_id="t", note="  ")
    take(session, case, "escalate", user="nina", role="nurse_reviewer", trace_id="t", note="Red flags unclear")
    assert (case.state, case.escalation_note) == ("escalated", "Red flags unclear")


def escalated(session):
    case = in_review(session)
    return take(session, case, "escalate", user="nina", role="nurse_reviewer", trace_id="t", note="Please review")


def test_as11_a_denial_needs_a_medical_director_a_reason_code_and_an_explanation(session):
    case = escalated(session)
    with pytest.raises(Invalid, match="needs a reason code"):
        take(session, case, "deny", user="dr.okafor", role="medical_director", trace_id="t", note=EXPLANATION)
    with pytest.raises(Invalid, match="at least 20 characters"):
        take(session, case, "deny", user="dr.okafor", role="medical_director", trace_id="t",
             reason_code="documentation_does_not_support", note="No.")
    take(session, case, "deny", user="dr.okafor", role="medical_director", trace_id="t",
         reason_code="documentation_does_not_support", note=EXPLANATION)
    assert (case.state, case.decision_reason_code, case.decision_explanation) == (
        "denied", "documentation_does_not_support", EXPLANATION)


def test_a_medical_director_can_approve_an_escalated_case(session):
    case = escalated(session)
    take(session, case, "approve", user="dr.okafor", role="medical_director", trace_id="t")
    assert case.state == "approved"


def test_a_medical_director_doesnt_take_cases_still_with_a_nurse(session):
    case = in_review(session)
    with pytest.raises(WrongState, match="decides escalated cases"):
        take(session, case, "approve", user="dr.okafor", role="medical_director", trace_id="t")


def test_a_nurse_doesnt_approve_an_escalated_case(session):
    case = escalated(session)
    with pytest.raises(WrongState, match="not escalated ones"):
        take(session, case, "approve", user="nina", role="nurse_reviewer", trace_id="t")


def test_an_intake_coordinator_withdraws_with_a_reason(session):
    case = new_case(session, documents=[])
    assert case.state == "pended"
    with pytest.raises(Invalid):
        take(session, case, "withdraw", user="ivy", role="intake_coordinator", trace_id="t")
    take(session, case, "withdraw", user="ivy", role="intake_coordinator", trace_id="t", note="Provider cancelled")
    assert (case.state, case.closed_reason) == ("withdrawn", "Provider cancelled")


def test_a_decided_case_cant_be_withdrawn(session):
    case = in_review(session)
    take(session, case, "approve", user="nina", role="nurse_reviewer", trace_id="t")
    with pytest.raises(WrongState, match="Can't withdraw a case that is approved"):
        take(session, case, "withdraw", user="ivy", role="intake_coordinator", trace_id="t", note="x")


@pytest.mark.parametrize("action", ["start_review", "approve", "escalate", "deny", "withdraw"])
@pytest.mark.parametrize("role", ["admin", "extractor", "connector"])
def test_admins_and_services_cant_decide_anything(session, action, role):
    case = new_case(session)
    with pytest.raises(NotAllowed):
        take(session, case, action, user="x", role=role, trace_id="t", note=EXPLANATION,
             reason_code="service_not_covered")
