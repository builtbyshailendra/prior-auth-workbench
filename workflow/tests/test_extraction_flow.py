"""Step 10: the extraction worker, the workflow's checks on its answers, and the Claude extractor.

No API key and no network: the Claude client is replaced by a fake that records the request.
"""
import json
import os
from datetime import timedelta
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.clocks import clock
from app.db import SessionLocal
from app.extraction import service as extraction
from app.extraction.baseline import BaselineExtractor
from app.extraction.claude import SCHEMA, ClaudeExtractor, ExtractionUnavailable, cost_usd
from app.worker import process_once
from tests.conftest import START
from tests.helpers import payload

EXTRACTOR = {"Authorization": f"Bearer {os.environ['EXTRACTOR_TOKEN']}"}


@pytest.fixture
def worker_mode(monkeypatch):
    monkeypatch.setenv("EXTRACTION_MODE", "worker")


def new_case(connector, **kwargs) -> int:
    return connector.post("/api/intake", json=payload(**kwargs)).json()["case_id"]


def claim(client, limit=5):
    response = client.post("/api/extraction/claim", json={"limit": limit}, headers=EXTRACTOR)
    assert response.status_code == 200, response.text
    return response.json()


def answer(client, case_id, **body):
    base = {"provider": "claude", "model": "claude-opus-5-5", "status": "ok", "facts": []}
    return client.post(f"/api/extraction/{case_id}", json={**base, **body}, headers=EXTRACTOR)


GOOD = [
    {"field": "conservative_therapy_weeks", "value": "6", "quote": "Completed 6 weeks of physical therapy without relief."},
    {"field": "red_flags_present", "value": "false", "quote": "Denies bowel or bladder changes."},
    {"field": "prior_imaging_done", "value": "unknown", "quote": ""},
]


# --- the workflow side ------------------------------------------------------------------

def test_a_complete_case_waits_for_extraction_and_stays_out_of_the_nurse_queue(worker_mode, connector, as_user):
    case_id = new_case(connector)
    assert connector.post("/api/intake", json=payload(member_id="SYN-M0002")).json()["state"] == "received"
    assert as_user("nina").get("/api/cases").json() == []
    case = as_user("ivy").get(f"/api/cases/{case_id}").json()
    assert (case["state"], case["extraction_status"]) == ("received", "pending")
    assert case["history"][-1]["event"] == "awaiting_extraction"


def test_the_worker_claims_jobs_with_documents_and_a_lease(worker_mode, connector, client):
    case_id = new_case(connector)
    jobs = claim(client)
    assert [j["case_id"] for j in jobs] == [case_id]
    assert jobs[0]["wanted"] == ["conservative_therapy_weeks", "red_flags_present", "prior_imaging_done", "symptom_duration_weeks"]
    assert "Completed 6 weeks of physical therapy" in jobs[0]["documents"][0]["text"]
    assert claim(client) == []  # leased for five minutes
    clock.set(START + timedelta(minutes=6))
    assert [j["case_id"] for j in claim(client)] == [case_id]


def test_answers_are_checked_against_the_documents_and_the_case_goes_to_review(worker_mode, connector, client, as_user):
    case_id = new_case(connector)
    claim(client)
    fake = {"field": "symptom_duration_weeks", "value": "12", "quote": "Back pain for 12 weeks."}  # AS-08: not in the note
    response = answer(client, case_id, facts=[*GOOD, fake], input_tokens=1500, output_tokens=300, cost_usd=0.012)
    assert response.status_code == 200
    assert response.json()["state"] == "ready_for_review"
    case = as_user("nina").get(f"/api/cases/{case_id}").json()
    facts = {f["field"]: f for f in case["facts"]}
    assert facts["conservative_therapy_weeks"]["value"] == 6
    assert facts["conservative_therapy_weeks"]["status"] == "verified"
    assert facts["conservative_therapy_weeks"]["method"] == "ai"
    assert facts["red_flags_present"]["value"] is False
    assert facts["prior_imaging_done"]["status"] == "not_documented"
    assert facts["symptom_duration_weeks"]["status"] == "dropped"
    assert facts["symptom_duration_weeks"]["value"] is None
    assert facts["symptom_duration_weeks"]["note"] == "The quote doesn't appear in any document"
    assert case["extraction"] == {"provider": "claude", "model": "claude-opus-5-5", "status": "ok", "verified": 2,
                                  "dropped": 1, "cost_usd": 0.012, "duration_ms": 0}
    extracted = next(e for e in case["history"] if e["event"] == "facts_extracted")
    assert extracted["detail"] == {"provider": "claude", "model": "claude-opus-5-5", "verified": 2, "dropped": 1,
                                   "not_documented": 1}


def test_as09_a_failed_extraction_sends_the_case_to_manual_entry(worker_mode, connector, client, as_user):
    case_id = new_case(connector)
    claim(client)
    response = answer(client, case_id, status="failed", error="ExtractionUnavailable: Timed out waiting for Claude")
    assert response.json()["extraction_status"] == "manual_needed"
    case = as_user("nina").get(f"/api/cases/{case_id}").json()
    assert (case["state"], case["facts"]) == ("ready_for_review", [])
    assert "extraction_failed" in [e["event"] for e in case["history"]]


def test_as09_if_the_worker_never_answers_the_sweep_gives_up_after_ten_minutes(worker_mode, connector, as_user):
    case_id = new_case(connector)
    clock.set(START + timedelta(minutes=9))
    with SessionLocal() as s:
        assert extraction.sweep(s) == 0
    clock.set(START + timedelta(minutes=11))
    with SessionLocal() as s:
        assert extraction.sweep(s) == 1
    case = as_user("nina").get(f"/api/cases/{case_id}").json()
    assert (case["state"], case["extraction_status"]) == ("ready_for_review", "manual_needed")
    assert case["extraction"]["status"] == "timed_out"


def test_an_answer_for_a_case_that_isnt_waiting_is_refused(worker_mode, connector, client):
    case_id = new_case(connector)
    claim(client)
    assert answer(client, case_id, facts=GOOD).status_code == 200
    assert answer(client, case_id, facts=GOOD).status_code == 409
    assert answer(client, 9999, facts=GOOD).status_code == 404


def test_only_the_extraction_worker_can_claim_or_answer(worker_mode, connector, as_user):
    case_id = new_case(connector)
    assert connector.post("/api/extraction/claim", json={}).status_code == 403
    assert as_user("nina").post("/api/extraction/claim", json={}).status_code == 403
    assert as_user("nina").post(f"/api/extraction/{case_id}", json={"provider": "claude", "model": "x", "status": "ok"}).status_code == 403


def test_services_without_checklist_facts_skip_extraction(worker_mode, connector):
    body = payload(service_code="97110", documents=[
        {"doc_type": "plan_of_care", "title": "Plan", "text": "Synthetic plan."},
        {"doc_type": "progress_note", "title": "Note", "text": "Synthetic note."},
    ])
    assert connector.post("/api/intake", json=body).json()["state"] == "ready_for_review"


def test_the_worker_end_to_end_with_the_rules_extractor(worker_mode, connector, client, as_user):
    case_id = new_case(connector)

    def post(path, body):
        response = client.post(path, json=body, headers=EXTRACTOR)
        return response.status_code, response.json()

    assert process_once(post, BaselineExtractor()) == 1
    case = as_user("nina").get(f"/api/cases/{case_id}").json()
    facts = {f["field"]: (f["value"], f["status"], f["method"]) for f in case["facts"]}
    assert facts["conservative_therapy_weeks"] == (6, "verified", "rules")
    assert facts["red_flags_present"] == (False, "verified", "rules")
    assert process_once(post, BaselineExtractor()) == 0


def test_a_crashing_extractor_reports_a_failure_instead_of_vanishing(worker_mode, connector, client, as_user):
    case_id = new_case(connector)

    class Broken:
        provider, model = "claude", "claude-opus-5-5"

        def extract(self, *args):
            raise ExtractionUnavailable("Can't reach the Claude API")

    def post(path, body):
        response = client.post(path, json=body, headers=EXTRACTOR)
        return response.status_code, response.json()

    process_once(post, Broken())
    assert as_user("nina").get(f"/api/cases/{case_id}").json()["extraction_status"] == "manual_needed"


# --- the Claude extractor, with a fake client --------------------------------------------------

class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(text='{"facts": []}', stop_reason="end_turn", error=None):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1200, output_tokens=250, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )
    messages = FakeMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_the_claude_request_uses_structured_output_low_effort_caching_and_fallback():
    client, messages = fake_client(json.dumps({"facts": [{"field": "epworth_score", "value": "14", "quote": "ESS 14/24 today."}]}))
    facts, usage = ClaudeExtractor(client=client).extract("95810", ["ESS 14/24 today."], ["epworth_score"])
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert '<document index="0">' in call["messages"][0]["content"]
    assert [(f.field, f.value, f.quote) for f in facts] == [("epworth_score", "14", "ESS 14/24 today.")]
    assert usage["cost_usd"] == cost_usd("claude-opus-5-5", 1200, 250) == 0.0098


@pytest.mark.parametrize("text, stop_reason, message", [
    ('{"facts": []}', "refusal", "declined"),
    ('{"facts": [', "max_tokens", "cut off"),
    ("not json", "end_turn", "didn't match the expected format"),
    ('{"facts": [{"field": "x"}]}', "end_turn", "didn't match the expected format"),
])
def test_unusable_replies_become_extraction_unavailable(text, stop_reason, message):
    client, _ = fake_client(text, stop_reason)
    with pytest.raises(ExtractionUnavailable, match=message):
        ClaudeExtractor(client=client).extract("95810", ["x"], ["epworth_score"])


def test_api_errors_become_extraction_unavailable():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    for error, message in [(anthropic.APITimeoutError(request=request), "Timed out"),
                           (anthropic.APIConnectionError(request=request), "Can't reach")]:
        client, _ = fake_client(error=error)
        with pytest.raises(ExtractionUnavailable, match=message):
            ClaudeExtractor(client=client).extract("95810", ["x"], ["epworth_score"])
