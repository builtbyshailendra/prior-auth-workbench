"""The extraction worker: a separate process with the least privilege that works.

    EXTRACTOR=claude EXTRACTOR_TOKEN=... WORKFLOW_URL=http://127.0.0.1:8000 python -m app.worker

It holds only the extractor token, so the workflow service lets it do two things:
claim cases waiting for extraction, and send back raw answers. It can't read queues,
change a case's state or decide anything. The workflow service checks every answer
against the documents before a person sees it.

EXTRACTOR: claude (needs ANTHROPIC_API_KEY) or rules (the regex baseline, no key).
POLL_SECONDS: how long to wait when there's nothing to do (default 5).
Logs one JSON line per case: IDs, counts and timings only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable

Post = Callable[[str, dict], tuple[int, object]]


def http_post(base_url: str, token: str) -> Post:
    def post(path: str, body: dict) -> tuple[int, object]:
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    return post


def make_extractor(name: str):
    if name == "claude":
        from app.extraction.claude import ClaudeExtractor

        return ClaudeExtractor()
    if name == "rules":
        from app.extraction.baseline import BaselineExtractor

        return BaselineExtractor()
    raise SystemExit(f"EXTRACTOR must be claude or rules, not {name!r}")


def log(**fields) -> None:
    print(json.dumps({"event": "extraction", **fields}), flush=True)


def process_once(post: Post, extractor, limit: int = 5) -> int:
    """Claim up to `limit` cases, extract, report. Returns how many cases it handled."""
    status, jobs = post("/api/extraction/claim", {"limit": limit})
    if status != 200:
        raise RuntimeError(f"Claim failed with {status}: {jobs}")
    for job in jobs:  # type: ignore[union-attr]
        started = time.perf_counter()
        documents = [d["text"] for d in job["documents"]]
        try:
            raw, usage = extractor.extract(job["service_code"], documents, job["wanted"])
            body = {
                "provider": extractor.provider,
                "model": extractor.model,
                "status": "ok",
                "facts": [{"field": f.field, "value": f.value, "quote": f.quote} for f in raw],
                "input_tokens": int(usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0)),
                "cost_usd": float(usage.get("cost_usd", 0.0)),
            }
        except Exception as error:  # any failure means a person enters the facts
            body = {"provider": extractor.provider, "model": extractor.model, "status": "failed",
                    "error": f"{type(error).__name__}: {error}"[:500]}
        body["duration_ms"] = int((time.perf_counter() - started) * 1000)
        code, answer = post(f"/api/extraction/{job['case_id']}", body)
        log(case_id=job["case_id"], status=body["status"], http=code, duration_ms=body["duration_ms"],
            facts=len(body.get("facts", [])), cost_usd=body.get("cost_usd", 0.0))
    return len(jobs)  # type: ignore[arg-type]


def main() -> None:
    token = os.environ.get("EXTRACTOR_TOKEN", "")
    if not token:
        sys.exit("Set EXTRACTOR_TOKEN")
    post = http_post(os.environ.get("WORKFLOW_URL", "http://127.0.0.1:8000"), token)
    extractor = make_extractor(os.environ.get("EXTRACTOR", "rules"))
    poll = float(os.environ.get("POLL_SECONDS", "5"))
    log(started=True, provider=extractor.provider, model=extractor.model)
    while True:
        try:
            handled = process_once(post, extractor)
        except (urllib.error.URLError, RuntimeError, ConnectionError) as error:
            log(error=str(error)[:200])
            handled = 0
        if handled == 0:
            time.sleep(poll)


if __name__ == "__main__":
    main()
