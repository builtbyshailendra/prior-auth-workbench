"""A simulated pilot: 200 synthetic requests through a running workflow service.

    python -m sim.pilot --url http://127.0.0.1:8011 --requests 200

What's real: the workflow service, its database, its checks and timestamps; the extraction
worker's code (run in-process here, with the rules baseline, since there's no API key);
the reports.

What's simulated, and says so in the results:
- Requests are sent in the internal format, as the connectors would send them. The connectors
  themselves are exercised separately (their tests and the CI ingest of every fixture).
- Receipt times are back-dated by this script, so decision times reflect the script's choices,
  not real reviewer speed.
- Reviewers are code. They correct facts against the labels the note generator wrote, and
  decide by an illustrative policy (not medical policy).

Environment: CONNECTOR_TOKEN, EXTRACTOR_TOKEN, DEMO_PASSWORD (as the service was started with).
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.extraction.baseline import BaselineExtractor
from app.worker import http_post, process_once
from eval.generate import lumbar, sleep

INELIGIBLE = ["SYN-M0007", "SYN-M0019", "SYN-M0033", "SYN-M0048"]
COVERED = [f"SYN-M{i:04d}" for i in range(1, 61) if f"SYN-M{i:04d}" not in INELIGIBLE + ["SYN-M0012", "SYN-M0041"]]
OUT = Path(__file__).resolve().parents[2] / "docs" / "delivery"


class User:
    def __init__(self, base: str, username: str, password: str):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        status, body = self.call("POST", "/api/auth/login", {"username": username, "password": password})
        if status != 200:
            raise SystemExit(f"Can't sign in as {username}: {status} {body}")

    def call(self, method: str, path: str, body: dict | None = None):
        request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                         method=method, headers={"Content-Type": "application/json",
                                                                 "X-Requested-With": "workbench"})
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()[:300]


def build_request(rng: random.Random, i: int, now: datetime) -> dict:
    roll = rng.random()
    service = "72148" if roll < 0.5 else "95810" if roll < 0.8 else "97110" if roll < 0.95 else "99213"
    expedited = rng.random() < 0.15
    if expedited:
        hours = rng.uniform(74, 90) if rng.random() < 0.05 else rng.uniform(1, 66)
    else:
        hours = rng.uniform(7.2 * 24, 8 * 24) if rng.random() < 0.05 else rng.uniform(2, 6.5 * 24)
    labels: dict = {}
    if service == "72148":
        notes, labels = lumbar(rng, 1000 + i)
        documents = [{"doc_type": "clinician_note", "title": "Clinic note", "text": notes[0]},
                     {"doc_type": "conservative_treatment_record", "title": "Treatment record",
                      "text": notes[1] if len(notes) > 1 else "SYNTHETIC RECORD (fiction). Treatment history as described in the clinic note."}]
        dx = ["M54.50"]
    elif service == "95810":
        notes, labels = sleep(rng, 1000 + i)
        documents = [{"doc_type": "clinician_note", "title": "Sleep clinic note", "text": notes[0]},
                     {"doc_type": "sleep_questionnaire", "title": "Sleep questionnaire",
                      "text": "SYNTHETIC QUESTIONNAIRE (fiction). Completed; the score is recorded in the clinic note."}]
        dx = ["G47.33"]
    elif service == "97110":
        documents = [{"doc_type": "plan_of_care", "title": "Plan of care", "text": "SYNTHETIC PLAN (fiction). 8 more visits."},
                     {"doc_type": "progress_note", "title": "Progress note", "text": "SYNTHETIC NOTE (fiction). Improving."}]
        dx = ["M25.561"]
    else:
        documents, dx = [], ["J06.9"]
    held_back = None
    if documents and rng.random() < 0.30:
        held_back = documents.pop()  # arrives later, or never
    member = rng.choice(INELIGIBLE) if rng.random() < 0.04 else rng.choice(COVERED)
    return {
        "body": {
            "source": rng.choice(["fhir", "x12", "fax", "crm"]),
            "source_id": f"sim-{i:04d}-{rng.randrange(10**8):08d}",
            "received_at": (now - timedelta(hours=hours)).isoformat(),
            "priority": "expedited" if expedited else "standard",
            "member": {"id": member, "name": "Simulated Member"},
            "provider": {"npi": "1234567890" if rng.random() < 0.03 else "1234567893", "name": "Synthetic Provider"},
            "service": {"code": service, "diagnosis_codes": dx,
                        "date_start": (now + timedelta(days=rng.randint(10, 60))).date().isoformat()},
            "documents": documents,
        },
        "held_back": held_back,
        "provider_answers": rng.random() < 0.8,
        "labels": labels,
        "service": service,
    }


def as_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def policy(service: str, labels: dict) -> bool:
    """Illustrative only: what the simulated nurse treats as clearly meeting the checklist."""
    if service == "72148":
        return (labels.get("conservative_therapy_weeks") or 0) >= 6 or labels.get("red_flags_present") is True
    if service == "95810":
        return (labels.get("epworth_score") or 0) >= 10 or labels.get("witnessed_apneas") is True
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    rng = random.Random(args.seed)
    now = datetime.now(UTC)
    password = os.environ.get("DEMO_PASSWORD", "demo-password")
    connector = http_post(base, os.environ["CONNECTOR_TOKEN"])
    extractor = http_post(base, os.environ["EXTRACTOR_TOKEN"])
    started = time.perf_counter()

    # 1. Intake
    sent = [build_request(rng, i, now) for i in range(args.requests)]
    outcomes: dict[str, int] = {}
    for r in sent:
        status, body = connector("/api/intake", r["body"])
        r["status"], r["case_id"] = status, body.get("case_id") if isinstance(body, dict) else None
        key = f"{status}:{body.get('state') if isinstance(body, dict) else 'rejected'}"
        outcomes[key] = outcomes.get(key, 0) + 1

    # 2. Providers answer the request for information (most of them)
    answered = 0
    for r in sent:
        if r["held_back"] and r["case_id"] and r["provider_answers"]:
            status, _ = connector(f"/api/cases/{r['case_id']}/documents", {"documents": [r["held_back"]]})
            answered += status == 200

    # 3. Extraction, by the worker's own code
    extracted = 0
    while True:
        handled = process_once(extractor, BaselineExtractor(), limit=20)
        extracted += handled
        if handled == 0:
            break

    # 4. Reviewers
    nurses = [User(base, "nina", password), User(base, "omar", password)]
    director = User(base, "dr.lee", password)
    tally = dict(reviewed=0, verified_correct=0, entered=0, corrected=0, approved=0, escalated=0, denied=0,
                 summaries_accepted=0, summaries_edited=0)
    for n, r in enumerate(x for x in sent if x["case_id"]):
        nurse = nurses[n % 2]
        status, case = nurse.call("GET", f"/api/cases/{r['case_id']}")
        if status != 200 or case["state"] != "ready_for_review":
            continue
        nurse.call("POST", f"/api/cases/{r['case_id']}/start_review", {})
        tally["reviewed"] += 1
        facts = {f["field"]: f for f in case["facts"]}
        changed = False
        for field in [f["name"] for f in case["checklist_fields"]]:
            label, fact = r["labels"].get(field), facts.get(field)
            if fact and fact["status"] == "verified" and fact["value"] == label:
                tally["verified_correct"] += 1
                continue
            if fact and fact["status"] == "not_documented" and label is None:
                continue
            if fact and fact["status"] == "verified":
                tally["corrected"] += 1
            else:
                tally["entered"] += 1
            nurse.call("POST", f"/api/review/{r['case_id']}/facts",
                       {"field": field, "value": as_text(label), "note": "Simulated reviewer: read from the note"})
            changed = True
        _, latest = nurse.call("GET", f"/api/cases/{r['case_id']}")
        if latest.get("summary"):
            if changed:
                nurse.call("POST", f"/api/review/{r['case_id']}/summary",
                           {"accepted": False, "edited_text": latest["summary"]["text"] + " Checked against the notes."})
                tally["summaries_edited"] += 1
            else:
                nurse.call("POST", f"/api/review/{r['case_id']}/summary", {"accepted": True})
                tally["summaries_accepted"] += 1
        if policy(r["service"], r["labels"]):
            nurse.call("POST", f"/api/cases/{r['case_id']}/approve", {})
            tally["approved"] += 1
        else:
            nurse.call("POST", f"/api/cases/{r['case_id']}/escalate", {"note": "Doesn't clearly meet the checklist"})
            tally["escalated"] += 1
            if rng.random() < 0.3:
                director.call("POST", f"/api/cases/{r['case_id']}/approve", {})
                tally["approved"] += 1
            else:
                reason = "conservative_treatment_not_tried" if r["service"] == "72148" else "documentation_does_not_support"
                director.call("POST", f"/api/cases/{r['case_id']}/deny",
                              {"reason_code": reason, "note": "Simulated medical director: the documented facts don't meet the illustrative checklist."})
                tally["denied"] += 1

    # 5. Reports
    admin = User(base, "admin", password)
    _, ops = admin.call("GET", "/api/reports/operations")
    _, cms = admin.call("GET", f"/api/reports/cms?year={now.year}")
    result = {
        "run_at": now.isoformat(timespec="seconds"),
        "seconds": round(time.perf_counter() - started, 1),
        "requests": args.requests,
        "seed": args.seed,
        "extractor": "rules baseline (no API key)",
        "intake_outcomes": outcomes,
        "rfi_answered_by_providers": answered,
        "extraction_jobs_handled": extracted,
        "reviewers": tally,
        "operations_report": ops,
        "cms_report": cms,
        "simulated": [
            "receipt times back-dated by the script",
            "reviewers and their decisions are code following an illustrative policy",
            "requests sent in the internal format, not through the connector adapters",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pilot-simulation.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("operations_report", "cms_report")}, indent=1))
    print(json.dumps(ops, indent=1))
    print(json.dumps(cms, indent=1))


if __name__ == "__main__":
    main()
