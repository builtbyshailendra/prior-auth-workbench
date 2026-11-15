"""Step 11: the drafted summary, manual fact entry and correction, and accept or edit tracking."""
import os

import pytest

from tests.helpers import payload

EXTRACTOR = {"Authorization": f"Bearer {os.environ['EXTRACTOR_TOKEN']}"}
FACTS = [
    {"field": "conservative_therapy_weeks", "value": "6", "quote": "Completed 6 weeks of physical therapy without relief."},
    {"field": "red_flags_present", "value": "false", "quote": "Denies bowel or bladder changes."},
    {"field": "symptom_duration_weeks", "value": "12", "quote": "Back pain for 12 weeks."},  # made up: dropped
]


@pytest.fixture
def reviewed_case(monkeypatch, connector, client, as_user):
    """A lumbar case with extracted facts, picked up by Nina."""
    monkeypatch.setenv("EXTRACTION_MODE", "worker")
    case_id = connector.post("/api/intake", json=payload()).json()["case_id"]
    client.post("/api/extraction/claim", json={}, headers=EXTRACTOR)
    client.post(f"/api/extraction/{case_id}", json={"provider": "claude", "model": "claude-opus-5-5", "status": "ok",
                                                    "facts": FACTS}, headers=EXTRACTOR)
    nina = as_user("nina")
    nina.post(f"/api/cases/{case_id}/start_review", json={})
    return case_id, nina


def sentences(case):
    return [s["text"] for s in case["summary"]["sentences"]]


def test_a_summary_is_drafted_from_the_checked_facts(reviewed_case):
    case_id, nina = reviewed_case
    case = nina.get(f"/api/cases/{case_id}").json()
    assert case["summary"]["method"] == "template"
    assert case["summary"]["review_status"] == "pending"
    assert sentences(case) == [
        "Lumbar spine MRI for SYN-M0001, standard request. All required documents received.",
        "Weeks of conservative treatment: 6 weeks (quoted from the documents).",
        "Red-flag symptoms: no (quoted from the documents).",
        "Prior imaging of the area: not documented.",
        "How long symptoms have lasted (weeks): an extracted answer couldn't be verified, so it needs checking by hand.",
        "1 answer(s) couldn't be verified; check the documents before deciding.",
    ]
    # Every sentence about a fact points at that fact.
    facts = {f["id"]: f["field"] for f in case["facts"]}
    assert [facts[i] for s in case["summary"]["sentences"][1:5] for i in s["fact_ids"]] == [
        "conservative_therapy_weeks", "red_flags_present", "prior_imaging_done", "symptom_duration_weeks"]


def test_a_reviewer_enters_a_fact_the_ai_couldnt_verify(reviewed_case):
    case_id, nina = reviewed_case
    case = nina.post(f"/api/review/{case_id}/facts",
                     json={"field": "symptom_duration_weeks", "value": "10", "note": "Clinic note, first line"}).json()
    fact = next(f for f in case["facts"] if f["field"] == "symptom_duration_weeks")
    assert (fact["value"], fact["method"], fact["status"], fact["entered_by"]) == (10, "manual", "entered", "nina")
    assert len([f for f in case["facts"] if f["field"] == "symptom_duration_weeks"]) == 1  # the dropped one is superseded
    assert "How long symptoms have lasted (weeks): 10 weeks (entered by the reviewer)." in sentences(case)
    entered = next(e for e in case["history"] if e["event"] == "fact_entered")
    assert entered["detail"] == {"field": "symptom_duration_weeks", "replaced": ["ai:dropped"]}


def test_a_reviewer_corrects_a_verified_ai_fact_and_the_original_is_kept_for_counting(reviewed_case, session):
    case_id, nina = reviewed_case
    nina.post(f"/api/review/{case_id}/facts", json={"field": "red_flags_present", "value": "true",
                                                    "note": "Therapy note mentions new numbness"})
    from sqlalchemy import select

    from app.models import Fact

    rows = session.scalars(select(Fact).where(Fact.case_id == case_id, Fact.field == "red_flags_present").order_by(Fact.id)).all()
    assert [(r.method, r.status, r.superseded, r.value) for r in rows] == [
        ("ai", "verified", True, False), ("manual", "entered", False, True)]


@pytest.mark.parametrize("body, message", [
    ({"field": "epworth_score", "value": "10", "note": "x note"}, "isn't a checklist fact for this service"),
    ({"field": "symptom_duration_weeks", "value": "ten", "note": "x note"}, "isn't a valid answer"),
    ({"field": "symptom_duration_weeks", "value": "10", "note": ""}, "Say where in the documents"),
])
def test_bad_manual_entries_are_refused(reviewed_case, body, message):
    case_id, nina = reviewed_case
    response = nina.post(f"/api/review/{case_id}/facts", json=body)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_accepting_and_editing_the_summary_are_recorded(reviewed_case):
    case_id, nina = reviewed_case
    case = nina.post(f"/api/review/{case_id}/summary", json={"accepted": True}).json()
    assert (case["summary"]["review_status"], case["summary"]["reviewed_by"]) == ("accepted", "nina")
    assert nina.post(f"/api/review/{case_id}/summary", json={"accepted": True}).status_code == 409
    # Changing a fact drafts a new summary, which can be edited.
    nina.post(f"/api/review/{case_id}/facts", json={"field": "symptom_duration_weeks", "value": "10", "note": "Clinic note"})
    assert nina.post(f"/api/review/{case_id}/summary", json={"accepted": False, "edited_text": "short"}).status_code == 422
    case = nina.post(f"/api/review/{case_id}/summary",
                     json={"accepted": False, "edited_text": "Six weeks of therapy, no red flags, ten weeks of pain."}).json()
    assert (case["summary"]["review_status"], case["summary"]["edited_text"]) == (
        "edited", "Six weeks of therapy, no red flags, ten weeks of pain.")
    results = [e["detail"]["result"] for e in case["history"] if e["event"] == "summary_reviewed"]
    assert results == ["accepted", "edited"]


def test_only_the_current_reviewer_can_change_facts(reviewed_case, as_user, connector):
    case_id, _ = reviewed_case
    body = {"field": "symptom_duration_weeks", "value": "10", "note": "Clinic note"}
    assert as_user("omar").post(f"/api/review/{case_id}/facts", json=body).status_code == 404  # not his case
    assert as_user("ivy").post(f"/api/review/{case_id}/facts", json=body).status_code == 403
    assert connector.post(f"/api/review/{case_id}/facts", json=body).status_code == 403


def test_a_case_with_no_extraction_still_gets_a_summary_that_says_so(connector, as_user):
    case_id = connector.post("/api/intake", json=payload()).json()["case_id"]  # extraction off: manual entry
    case = as_user("nina").get(f"/api/cases/{case_id}").json()
    assert case["extraction_status"] == "manual_needed"
    assert sentences(case) == ["Lumbar spine MRI for SYN-M0001, standard request. All required documents received."]
