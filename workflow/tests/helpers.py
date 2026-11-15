"""Synthetic request payloads for tests. Every person and note here is made up."""
from __future__ import annotations

import itertools

_ids = itertools.count(1)

LUMBAR_DOCS = [
    {
        "doc_type": "clinician_note",
        "title": "Clinic note, 2026-11-02",
        "text": "Synthetic note. Low back pain for 10 weeks radiating to the left leg. "
                "Completed 6 weeks of physical therapy without relief. Denies bowel or bladder changes.",
    },
    {
        "doc_type": "conservative_treatment_record",
        "title": "Physical therapy discharge summary",
        "text": "Synthetic record. 12 sessions over 6 weeks. Home exercise program continued.",
    },
]

SLEEP_DOCS = [
    {"doc_type": "clinician_note", "title": "Clinic note", "text": "Synthetic note. Loud snoring, witnessed apneas."},
    {"doc_type": "sleep_questionnaire", "title": "Sleep questionnaire", "text": "Synthetic questionnaire. Score 14 of 24."},
]


def payload(
    *,
    source: str = "fax",
    source_id: str | None = None,
    priority: str = "standard",
    member_id: str = "SYN-M0001",
    npi: str = "1234567893",
    service_code: str = "72148",
    diagnosis_codes: list[str] | None = None,
    date_start: str = "2026-12-01",
    documents: list[dict] | None = None,
    received_at: str | None = None,
) -> dict:
    body = {
        "source": source,
        "source_id": source_id or f"{source}-{next(_ids):05d}",
        "priority": priority,
        "member": {"id": member_id, "name": "Synthetic Member"},
        "provider": {"npi": npi, "name": "Synthetic Orthopedics Group"},
        "service": {"code": service_code, "diagnosis_codes": diagnosis_codes or ["M54.50"], "date_start": date_start},
        "documents": LUMBAR_DOCS if documents is None else documents,
    }
    if received_at:
        body["received_at"] = received_at
    return body
