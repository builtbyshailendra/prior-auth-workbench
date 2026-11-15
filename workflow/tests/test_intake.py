"""Step 3: intake, checklists, requests for information, duplicates. Scenario IDs from docs/discovery/06."""
import threading
from datetime import datetime, timedelta

from sqlalchemy import func, select, text

from app import catalogue
from app.db import SessionLocal
from app.intake import receive
from app.models import Case, Submission
from app.schemas import IntakeRequest
from tests.helpers import SLEEP_DOCS, payload


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_as01_complete_standard_request_becomes_ready_for_review(connector, as_user):
    response = connector.post("/api/intake", json=payload(), headers={"X-Trace-Id": "trace-as01"})
    assert response.status_code == 201
    assert response.json()["outcome"] == "created"
    assert response.headers["X-Trace-Id"] == "trace-as01"
    case = as_user("nina").get(f"/api/cases/{response.json()['case_id']}").json()
    assert case["state"] == "ready_for_review"
    assert case["extraction_status"] == "manual_needed"
    received = datetime.fromisoformat(case["received_at"])
    assert datetime.fromisoformat(case["due_at"]) - received == timedelta(days=7)
    assert [(e["event"], e["to"]) for e in case["history"]] == [
        ("received", "received"),
        ("ready_for_review", "ready_for_review"),
    ]
    assert {e["trace_id"] for e in case["history"]} == {"trace-as01"}


def test_a_connector_gets_a_compact_answer_without_clinical_detail(connector):
    body = connector.post("/api/intake", json=payload(documents=[])).json()
    assert set(body) == {"outcome", "case_id", "state", "due_at", "missing"}
    assert body["missing"] == ["clinician_note", "conservative_treatment_record"]


def test_as02_missing_documents_are_asked_for_all_at_once(connector, as_user):
    ivy = as_user("ivy")
    created = connector.post("/api/intake", json=payload(service_code="95810", diagnosis_codes=["G47.33"], documents=[])).json()
    case = ivy.get(f"/api/cases/{created['case_id']}").json()
    assert case["state"] == "pended"
    assert [m["type"] for m in case["missing"]] == ["clinician_note", "sleep_questionnaire"]
    assert case["rfi_count"] == 1

    assert connector.post(f"/api/cases/{case['id']}/documents", json={"documents": SLEEP_DOCS}).json()["state"] == "ready_for_review"
    case = ivy.get(f"/api/cases/{case['id']}").json()
    assert case["rfi_count"] == 1
    assert case["missing"] == []
    assert case["rfis"][0]["resolved_at"] is not None
    assert [e["event"] for e in case["history"]] == [
        "received", "pended", "documents_received", "rechecked", "ready_for_review",
    ]


def test_some_documents_keep_the_case_pended_and_update_the_request(connector):
    case = connector.post("/api/intake", json=payload(service_code="95810", diagnosis_codes=["G47.33"], documents=[])).json()
    after = connector.post(f"/api/cases/{case['case_id']}/documents", json={"documents": SLEEP_DOCS[:1]}).json()
    assert (after["state"], after["missing"]) == ("pended", ["sleep_questionnaire"])


def test_as04_member_not_covered_on_the_date_is_closed_not_denied(connector, as_user):
    # SYN-M0007's coverage ended on 2026-10-31.
    created = connector.post("/api/intake", json=payload(member_id="SYN-M0007")).json()
    case = as_user("ivy").get(f"/api/cases/{created['case_id']}").json()
    assert case["state"] == "closed_ineligible"
    assert case["closed_reason"] == "Member SYN-M0007 isn't covered on 2026-12-01"
    assert case["decision"] is None


def test_a_member_the_plan_has_never_heard_of_is_not_eligible(connector):
    assert connector.post("/api/intake", json=payload(member_id="SYN-M9999")).json()["state"] == "closed_ineligible"


def test_coverage_gaps_count(connector):
    # SYN-M0012 lapsed on 2026-06-30 and re-enrolls on 2027-01-01.
    assert connector.post("/api/intake", json=payload(member_id="SYN-M0012")).json()["state"] == "closed_ineligible"
    later = connector.post("/api/intake", json=payload(member_id="SYN-M0012", date_start="2027-01-05")).json()
    assert later["state"] == "ready_for_review"


def test_as05_service_without_authorization_is_closed_with_the_catalogue_version(connector, as_user):
    created = connector.post("/api/intake", json=payload(service_code="99213", documents=[])).json()
    case = as_user("ivy").get(f"/api/cases/{created['case_id']}").json()
    assert case["state"] == "closed_no_auth"
    version = catalogue.load().version
    assert case["closed_reason"] == f"Service 99213 doesn't need authorization (catalogue {version})"
    assert case["history"][-1]["detail"] == {"catalogue_version": version}


def test_as06_same_request_from_two_channels_opens_one_case(connector, as_user, session):
    first = connector.post("/api/intake", json=payload(source="fax"))
    second = connector.post("/api/intake", json=payload(source="x12"))
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["outcome"] == "linked"
    assert second.json()["case_id"] == first.json()["case_id"]
    case = as_user("nina").get(f"/api/cases/{first.json()['case_id']}").json()
    assert [s["source"] for s in case["submissions"]] == ["fax", "x12"]
    assert "duplicate_linked" in [e["event"] for e in case["history"]]
    assert count(session, Case) == 1


def test_a_duplicate_can_bring_the_missing_documents(connector):
    assert connector.post("/api/intake", json=payload(source="fax", documents=[])).json()["state"] == "pended"
    linked = connector.post("/api/intake", json=payload(source="x12")).json()
    assert (linked["outcome"], linked["state"]) == ("linked", "ready_for_review")


def test_replaying_the_same_message_is_harmless(connector, session):
    body = payload(source_id="fax-replay-1")
    assert connector.post("/api/intake", json=body).json()["outcome"] == "created"
    replay = connector.post("/api/intake", json=body)
    assert (replay.status_code, replay.json()["outcome"]) == (200, "replayed")
    assert count(session, Submission) == 1


def test_a_closed_case_doesnt_block_a_new_request(connector, session):
    connector.post("/api/intake", json=payload(service_code="99213", documents=[]))
    connector.post("/api/intake", json=payload(service_code="99213", documents=[]))
    assert count(session, Case) == 2


def test_as07_invalid_npi_is_rejected_with_a_usable_reason(connector, session):
    response = connector.post("/api/intake", json=payload(npi="1234567890"))
    assert response.status_code == 422
    assert response.json()["problems"] == [
        {"field": "provider_npi", "code": "npi_check_digit", "message": "Provider NPI check digit is invalid"}
    ]
    assert count(session, Case) == 0


def test_unknown_fields_are_refused(connector):
    body = payload()
    body["surprise"] = True
    assert connector.post("/api/intake", json=body).status_code == 422


def test_documents_for_a_closed_case_are_refused(connector):
    case = connector.post("/api/intake", json=payload(service_code="99213", documents=[])).json()
    response = connector.post(f"/api/cases/{case['case_id']}/documents", json={"documents": SLEEP_DOCS})
    assert response.status_code == 409
    assert response.json()["detail"] == f"Case {case['case_id']} is closed no auth and can't take new documents"


def test_simultaneous_duplicates_open_exactly_one_case(db):
    cat = catalogue.load()
    barrier = threading.Barrier(4)
    outcomes = []

    def send(i):
        with SessionLocal() as s:
            # Connect first, so all four really run at once after the barrier.
            s.execute(text("SELECT 1"))
            barrier.wait()
            result = receive(s, IntakeRequest(**payload(source="crm", source_id=f"crm-race-{i}")),
                             catalogue=cat, actor="test", role="connector", trace_id=f"t{i}")
            outcomes.append(result.outcome)

    threads = [threading.Thread(target=send, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["created", "linked", "linked", "linked"]
    with SessionLocal() as s:
        assert count(s, Case) == 1
        assert count(s, Submission) == 4


def test_the_queue_is_sorted_by_deadline(connector, as_user):
    connector.post("/api/intake", json=payload(member_id="SYN-M0001", received_at="2026-11-15T09:00:00Z"))
    connector.post("/api/intake", json=payload(member_id="SYN-M0002", priority="expedited"))
    queue = as_user("nina").get("/api/cases").json()
    # The expedited request came in a day later but is due four days sooner.
    assert [c["member"]["id"] for c in queue] == ["SYN-M0002", "SYN-M0001"]
