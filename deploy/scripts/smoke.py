#!/usr/bin/env python3
"""Walk one request through the whole system against a running copy.

    CONNECTOR_TOKEN=... DEMO_PASSWORD=... python3 deploy/scripts/smoke.py http://127.0.0.1:3000

Through the web app's /api proxy, so one run checks the web server, the proxy, the
workflow service, the extraction worker and the database together:
1. a connector sends a complete request
2. the worker extracts facts and the case reaches the nurse queue (waits up to WAIT seconds)
3. a nurse picks it up and approves it
Standard library only. Exit code 1 on any failure.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000").rstrip("/")
TOKEN = os.environ["CONNECTOR_TOKEN"]
PASSWORD = os.environ.get("DEMO_PASSWORD", "demo-password")
WAIT = float(os.environ.get("WAIT", "90"))
EXPECT = os.environ.get("EXPECT_EXTRACTION", "complete")  # or manual_needed


class Client:
    def __init__(self, token: str | None = None):
        self.token = token
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        headers = {"Content-Type": "application/json", "X-Requested-With": "workbench"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                         method=method, headers=headers)
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()[:300]


def expect(what: str, result: tuple[int, object], *statuses: int):
    status, body = result
    if status not in statuses:
        sys.exit(f"FAIL {what}: got {status}: {body}")
    print(f"ok   {what}")
    return body


def main() -> None:
    connector = Client(TOKEN)
    member = f"SYN-M{random.randint(1, 6):04d}"
    day = f"2027-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    created = expect("connector sends a complete request", connector.call("POST", "/api/intake", {
        "source": "api",
        "source_id": f"smoke-{time.time_ns()}",
        "priority": "standard",
        "member": {"id": member, "name": "Smoke Test"},
        "provider": {"npi": "1234567893", "name": "Synthetic Spine Clinic"},
        "service": {"code": "72148", "diagnosis_codes": ["M54.50"], "date_start": day},
        "documents": [
            {"doc_type": "clinician_note", "title": "Clinic note",
             "text": "Synthetic note. Low back pain for 10 weeks. Completed 6 weeks of physical therapy without relief. "
                     "Denies bowel or bladder changes."},
            {"doc_type": "conservative_treatment_record", "title": "Therapy record", "text": "Synthetic. 12 visits over 6 weeks."},
        ],
    }), 200, 201)
    case_id = created["case_id"]

    nurse = Client()
    expect("nurse signs in", nurse.call("POST", "/api/auth/login", {"username": "nina", "password": PASSWORD}), 200)
    deadline = time.monotonic() + WAIT
    case: dict = {}
    while time.monotonic() < deadline:
        status, case = nurse.call("GET", f"/api/cases/{case_id}")
        if status == 200 and case["state"] == "ready_for_review":  # type: ignore[index]
            break
        time.sleep(2)
    else:
        sys.exit(f"FAIL case {case_id} didn't reach the nurse queue within {WAIT:.0f}s")
    print(f"ok   case {case_id} reached the nurse queue (extraction: {case['extraction_status']})")
    if case["extraction_status"] != EXPECT:
        sys.exit(f"FAIL expected extraction {EXPECT}, got {case['extraction_status']}")
    if EXPECT == "complete":
        verified = [f["field"] for f in case["facts"] if f["status"] == "verified"]
        if "conservative_therapy_weeks" not in verified:
            sys.exit(f"FAIL no verified therapy fact: {case['facts']}")
        print(f"ok   verified facts: {', '.join(verified)}")
    expect("nurse picks it up", nurse.call("POST", f"/api/cases/{case_id}/start_review", {}), 200)
    decided = expect("nurse approves it", nurse.call("POST", f"/api/cases/{case_id}/approve", {}), 200)
    if decided["state"] != "approved":
        sys.exit(f"FAIL state is {decided['state']}")
    print(f"ok   case {case_id} approved; {len(decided['history'])} audit events")


if __name__ == "__main__":
    main()
