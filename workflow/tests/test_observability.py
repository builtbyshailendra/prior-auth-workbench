"""Step 12: logs and metrics."""
import json
import logging

from tests.helpers import payload


def test_metrics_count_cases_by_state_and_risk(connector, client):
    connector.post("/api/intake", json=payload())
    connector.post("/api/intake", json=payload(member_id="SYN-M0002", documents=[]))
    text = client.get("/metrics").text
    assert 'priorauth_cases{state="ready_for_review"} 1.0' in text
    assert 'priorauth_cases{state="pended"} 1.0' in text
    assert 'priorauth_open_cases_by_risk{priority="standard",risk="on_track"} 2.0' in text


def test_request_metrics_use_route_patterns_not_ids(connector, client, as_user):
    case_id = connector.post("/api/intake", json=payload()).json()["case_id"]
    as_user("nina").get(f"/api/cases/{case_id}")
    text = client.get("/metrics").text
    assert 'route="/api/cases/{case_id}"' in text
    assert f'/api/cases/{case_id}"' not in text
    assert 'route="/metrics"' not in text


def test_json_logs_carry_the_trace_id_and_no_patient_details(connector, monkeypatch, caplog):
    monkeypatch.setenv("LOG_FORMAT", "json")
    with caplog.at_level(logging.INFO, logger="workflow.http"):
        connector.post("/api/intake", json=payload(), headers={"X-Trace-Id": "trace-log-1"})
    lines = [json.loads(r.message) for r in caplog.records if r.name == "workflow.http"]
    assert lines == [{"event": "http", "method": "POST", "route": "/api/intake", "status": 201,
                      "ms": lines[0]["ms"], "trace_id": "trace-log-1"}]
    assert "Synthetic Member" not in caplog.text and "physical therapy" not in caplog.text
