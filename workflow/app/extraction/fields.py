"""The checklist facts the extraction step looks for, per service.

Each fact is an integer or a yes/no. "Not documented" is a valid answer, and the
right one whenever the notes don't say. These definitions are illustrative, not
medical policy.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    kind: str  # "integer" or "boolean"
    label: str
    meaning: str


FIELDS: dict[str, FieldSpec] = {
    f.name: f
    for f in [
        FieldSpec("conservative_therapy_weeks", "integer", "Weeks of conservative treatment",
                  "How many weeks of physical therapy or supervised conservative treatment the notes say were completed. "
                  "0 if they say none was tried."),
        FieldSpec("red_flags_present", "boolean", "Red-flag symptoms",
                  "Whether the notes report red-flag symptoms (for example new bowel or bladder dysfunction, saddle numbness, "
                  "fever, history of cancer, progressive weakness). False if the notes say these are absent."),
        FieldSpec("prior_imaging_done", "boolean", "Prior imaging of the area",
                  "Whether the notes report earlier imaging (X-ray, CT or MRI) of the lumbar spine. False if they say there was none."),
        FieldSpec("symptom_duration_weeks", "integer", "How long symptoms have lasted (weeks)",
                  "How many weeks the current symptoms have lasted, if stated in weeks."),
        FieldSpec("epworth_score", "integer", "Sleep questionnaire score",
                  "The Epworth Sleepiness Scale total score, 0 to 24."),
        FieldSpec("home_sleep_test_done", "boolean", "Home sleep apnea test done",
                  "Whether a home sleep apnea test was done. False if the notes say it wasn't."),
        FieldSpec("witnessed_apneas", "boolean", "Witnessed pauses in breathing",
                  "Whether someone has seen the patient stop breathing or pause in breathing during sleep. "
                  "False if the notes say no."),
    ]
}


def fields_for(service_facts: tuple[str, ...]) -> list[FieldSpec]:
    return [FIELDS[name] for name in service_facts if name in FIELDS]
