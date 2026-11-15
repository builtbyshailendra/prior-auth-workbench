"""Writes the labelled test set: 40 synthetic clinical notes and the correct answers.

    python -m eval.generate

Every note is fiction, built from sentence templates whose meaning is known, so the
labels can't drift from the text. Some templates are deliberately awkward:
- a negation and a red flag in the same sentence
- an MRI mentioned only in the plan, not as earlier imaging
- an old questionnaire score next to today's
- "no one has witnessed" when the patient lives alone, which means unknown, not "no"

Deterministic: the same seed gives the same files.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
WORDS = {4: "four", 6: "six", 8: "eight", 10: "ten", 12: "twelve", 14: "fourteen"}
FIRST = ["Avery", "Jordan", "Riley", "Morgan", "Casey", "Quinn", "Rowan", "Emerson", "Harper", "Sawyer", "Reese", "Dakota"]
LAST = ["Okonkwo", "Lindqvist", "Ferreira", "Nakamura", "Brennan", "Adeyemi", "Castellano", "Whitfield", "Petrov", "Iyer"]


def pick(options: list, i: int, step: int):
    return options[(i * step + step // 2) % len(options)]


def header(rng: random.Random, i: int, kind: str) -> str:
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    return (f"SYNTHETIC {kind} - fiction written for software testing, not a real patient.\n"
            f"Patient: {name} (SYN-M{100 + i:04d}). Visit date: 2026-11-{(i % 27) + 1:02d}.\n")


def lumbar(rng: random.Random, i: int) -> tuple[list[str], dict]:
    labels: dict = {}
    side = rng.choice(["left", "right"])
    hpi: list[str] = []
    extra_docs: list[str] = []

    duration = pick([None, 6, 8, 10, 12, 14], i, 5)
    style = pick(["for", "history", "ongoing"], i, 7)
    if duration is None:
        hpi.append(f"Low back pain radiating to the {side} leg.")
    elif style == "for":
        hpi.append(f"Low back pain radiating to the {side} leg for {duration} weeks.")
    elif style == "history":
        hpi.append(f"{duration}-week history of low back pain radiating to the {side} leg.")
    else:
        hpi.append(f"Low back pain radiating to the {side} leg, ongoing for {WORDS[duration]} weeks.")
    labels["symptom_duration_weeks"] = duration

    therapy = pick(["weeks", "pt_x", "visits", "none", "not_started", "silent", "home_only"], i, 3)
    weeks = pick([4, 6, 8], i, 2)
    if therapy == "weeks":
        hpi.append(f"Completed {weeks} weeks of physical therapy without lasting relief.")
        labels["conservative_therapy_weeks"] = weeks
    elif therapy == "pt_x":
        hpi.append(f"PT x {weeks} wks with minimal improvement.")
        labels["conservative_therapy_weeks"] = weeks
    elif therapy == "visits":
        extra_docs.append("SYNTHETIC PHYSICAL THERAPY DISCHARGE SUMMARY - fiction.\n"
                          f"{weeks * 2} visits over {weeks} weeks. Home program continued. Pain 6/10 at discharge.\n")
        labels["conservative_therapy_weeks"] = weeks
    elif therapy == "none":
        hpi.append("Has not tried physical therapy.")
        labels["conservative_therapy_weeks"] = 0
    elif therapy == "not_started":
        hpi.append("Physical therapy was recommended at the last visit but has not been started.")
        labels["conservative_therapy_weeks"] = 0
    elif therapy == "home_only":
        hpi.append("Doing home exercises from a handout.")
        labels["conservative_therapy_weeks"] = None
    else:
        labels["conservative_therapy_weeks"] = None

    flags = pick(["neg_all", "neg_simple", "pos", "trap_mixed", "silent", "cancer"], i, 5)
    if flags == "neg_all":
        hpi.append("Denies bowel or bladder changes, saddle numbness or fever.")
        labels["red_flags_present"] = False
    elif flags == "neg_simple":
        hpi.append("No bowel or bladder dysfunction.")
        labels["red_flags_present"] = False
    elif flags == "pos":
        hpi.append("Reports new urinary retention and numbness in the saddle area.")
        labels["red_flags_present"] = True
    elif flags == "trap_mixed":
        hpi.append("No fever, but reports new saddle numbness since Tuesday.")
        labels["red_flags_present"] = True
    elif flags == "cancer":
        hpi.append("History of cancer, treated in 2019.")
        labels["red_flags_present"] = True
    else:
        labels["red_flags_present"] = None

    imaging = pick(["xray", "none", "silent", "ct"], i, 3)
    if imaging == "xray":
        hpi.append(f"Lumbar X-ray on 2026-{(i % 9) + 1:02d}-1{i % 9} showed mild degenerative changes.")
        labels["prior_imaging_done"] = True
    elif imaging == "none":
        hpi.append("No prior imaging of the spine.")
        labels["prior_imaging_done"] = False
    elif imaging == "ct":
        hpi.append("CT of the lumbar spine last year was unremarkable.")
        labels["prior_imaging_done"] = True
    else:
        labels["prior_imaging_done"] = None

    exam = f"Exam: straight leg raise positive on the {side}; strength 5/5 in both legs; reflexes symmetric."
    plan = "Plan: request MRI of the lumbar spine and review after results."
    note = header(rng, i, "CLINIC NOTE") + "History: " + " ".join(hpi) + "\n" + exam + "\n" + plan + "\n"
    return [note, *extra_docs], labels


def sleep(rng: random.Random, i: int) -> tuple[list[str], dict]:
    labels: dict = {}
    lines: list[str] = ["Loud snoring for several years and daytime sleepiness."]

    score = pick([None, 9, 12, 14, 16, 18, 20], i, 3)
    style = pick(["single", "ess", "prior_and_now"], i, 2)
    if score is None:
        pass
    elif style == "single":
        lines.append(f"Epworth Sleepiness Scale score of {score}.")
    elif style == "ess":
        lines.append(f"ESS {score}/24 today.")
    else:
        lines.append(f"Epworth was {score - 6} last year and is {score} today.")
    labels["epworth_score"] = score

    home = pick(["done", "not_done", "planned", "silent"], i, 3)
    if home == "done":
        lines.append("Home sleep apnea test on 2026-09-20 was inconclusive.")
        labels["home_sleep_test_done"] = True
    elif home == "not_done":
        lines.append("Has not had a home sleep test.")
        labels["home_sleep_test_done"] = False
    elif home == "planned":
        lines.append("A home sleep test will be arranged if the lab study is not approved.")
        labels["home_sleep_test_done"] = False
    else:
        labels["home_sleep_test_done"] = None

    seen = pick(["seen", "not_seen", "lives_alone", "silent"], i, 1)
    if seen == "seen":
        lines.append("Partner reports pauses in breathing at night.")
        labels["witnessed_apneas"] = True
    elif seen == "not_seen":
        lines.append("Bed partner has not noticed any pauses in breathing.")
        labels["witnessed_apneas"] = False
    elif seen == "lives_alone":
        lines.append("Lives alone; no one has witnessed whether breathing stops at night.")
        labels["witnessed_apneas"] = None
    else:
        labels["witnessed_apneas"] = None

    note = header(rng, i, "SLEEP CLINIC NOTE") + "History: " + " ".join(lines) + "\nPlan: in-lab polysomnography.\n"
    return [note], labels


def main() -> None:
    rng = random.Random(20261116)
    cases = []
    notes_dir = OUT / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 41):
        case_id = f"N{i:03d}"
        service, (docs, labels) = ("72148", lumbar(rng, i)) if i <= 25 else ("95810", sleep(rng, i))
        files = []
        for j, text in enumerate(docs, 1):
            path = notes_dir / f"{case_id}-{j}.txt"
            path.write_text(text, encoding="utf-8", newline="\n")
            files.append(f"notes/{path.name}")
        cases.append({"id": case_id, "service_code": service, "documents": files, "labels": labels})
    (OUT / "labels.json").write_text(json.dumps({"seed": 20261116, "cases": cases}, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")
    print(f"Wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
