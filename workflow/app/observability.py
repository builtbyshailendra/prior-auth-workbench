"""Logs and metrics.

Every request logs one JSON line (when LOG_FORMAT=json): method, route pattern, status,
duration and trace ID. Never a member name, never note text, never a case's contents.

/metrics serves Prometheus text: request counts and durations by route pattern, plus
counts read from the database when Prometheus asks (cases by state and deadline risk,
extraction outcomes, facts by source, summary reviews). /metrics isn't under /api, so the
web app doesn't proxy it; only something inside the network can scrape it.
"""
from __future__ import annotations

import json
import logging
import os
import time

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

from app.clocks import clock, risk
from app.db import SessionLocal
from app.models import OPEN_STATES, Case, ExtractionRun, Fact, Summary

log = logging.getLogger("workflow.http")

HTTP_REQUESTS = Counter("priorauth_http_requests", "HTTP requests handled", ["method", "route", "status"])
HTTP_SECONDS = Histogram("priorauth_http_request_seconds", "Time to handle a request", ["method", "route"])


class WorkflowCollector:
    """Counts read from the database at scrape time."""

    def describe(self):
        # Declared up front, so registering the collector doesn't query the database.
        return [
            GaugeMetricFamily("priorauth_cases", "Cases by state", labels=["state"]),
            GaugeMetricFamily("priorauth_open_cases_by_risk", "Open cases by deadline risk", labels=["priority", "risk"]),
            GaugeMetricFamily("priorauth_extraction_runs", "Extraction runs by outcome", labels=["provider", "status"]),
            GaugeMetricFamily("priorauth_facts", "Current facts by source and status", labels=["method", "status"]),
            GaugeMetricFamily("priorauth_summaries_reviewed", "Current summaries by review result", labels=["review_status"]),
        ]

    def collect(self):
        cases = GaugeMetricFamily("priorauth_cases", "Cases by state", labels=["state"])
        by_risk = GaugeMetricFamily("priorauth_open_cases_by_risk", "Open cases by deadline risk", labels=["priority", "risk"])
        runs = GaugeMetricFamily("priorauth_extraction_runs", "Extraction runs by outcome", labels=["provider", "status"])
        facts = GaugeMetricFamily("priorauth_facts", "Current facts by source and status", labels=["method", "status"])
        summaries = GaugeMetricFamily("priorauth_summaries_reviewed", "Current summaries by review result",
                                      labels=["review_status"])
        with SessionLocal() as session:
            for state, n in session.execute(select(Case.state, func.count()).group_by(Case.state)):
                cases.add_metric([state], n)
            now = clock.now()
            counts: dict[tuple[str, str], int] = {}
            for priority, due in session.execute(select(Case.priority, Case.due_at).where(Case.state.in_(OPEN_STATES))):
                key = (priority, risk(priority, due, now))
                counts[key] = counts.get(key, 0) + 1
            for (priority, level), n in counts.items():
                by_risk.add_metric([priority, level], n)
            for provider, status, n in session.execute(
                    select(ExtractionRun.provider, ExtractionRun.status, func.count())
                    .group_by(ExtractionRun.provider, ExtractionRun.status)):
                runs.add_metric([provider, status], n)
            for method, status, n in session.execute(
                    select(Fact.method, Fact.status, func.count()).where(Fact.superseded.is_(False))
                    .group_by(Fact.method, Fact.status)):
                facts.add_metric([method, status], n)
            for status, n in session.execute(
                    select(Summary.review_status, func.count()).where(Summary.superseded.is_(False))
                    .group_by(Summary.review_status)):
                summaries.add_metric([status], n)
        return [cases, by_risk, runs, facts, summaries]


REGISTRY.register(WorkflowCollector())


async def record(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    pattern = getattr(route, "path", "unmatched")
    if pattern != "/metrics":
        elapsed = time.perf_counter() - started
        HTTP_REQUESTS.labels(request.method, pattern, str(response.status_code)).inc()
        HTTP_SECONDS.labels(request.method, pattern).observe(elapsed)
        if os.environ.get("LOG_FORMAT") == "json":
            log.info(json.dumps({
                "event": "http", "method": request.method, "route": pattern, "status": response.status_code,
                "ms": round(elapsed * 1000, 1), "trace_id": getattr(request.state, "trace_id", None),
            }))
    return response


def endpoint() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
