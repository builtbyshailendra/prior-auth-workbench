"""Scores an extractor against the labelled test set.

    python -m eval.run --provider rules
    python -m eval.run --provider claude        # needs ANTHROPIC_API_KEY; costs a little (see README)

For every note and every checklist fact it compares the checked answer (after quote
verification) with the label. "Not documented" is an answer too.

What the numbers mean:
- correct:       the checked answer equals the label (including "not documented" when the label is empty)
- found:         of the facts the note does contain, how many were found with the right value
- false fills:   the note doesn't say, but a value was given anyway. The most dangerous error
- wrong values:  the note says one thing, the extractor said another
- dropped:       an answer failed verification (bad quote, number not in quote, invalid value)
- failures:      the extractor errored or timed out; in the app those cases go to manual entry
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app import catalogue
from app.extraction.verify import check

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"


def make_extractor(name: str, model: str | None):
    if name == "rules":
        from app.extraction.baseline import BaselineExtractor

        return BaselineExtractor()
    if name == "claude":
        from app.extraction.claude import ClaudeExtractor

        return ClaudeExtractor(model=model) if model else ClaudeExtractor()
    raise SystemExit(f"Unknown provider {name}")


def score(provider: str, model: str | None = None, limit: int | None = None) -> dict:
    cat = catalogue.load()
    extractor = make_extractor(provider, model)
    cases = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))["cases"][:limit]
    totals = dict(slots=0, correct=0, present=0, found=0, false_fills=0, wrong_values=0, dropped=0)
    failures = 0
    usage = dict(input_tokens=0, output_tokens=0, cost_usd=0.0)
    rows = []
    started = time.perf_counter()
    for case in cases:
        documents = [(DATA / f).read_text(encoding="utf-8") for f in case["documents"]]
        wanted = list(cat.service(case["service_code"]).facts)
        try:
            raw, used = extractor.extract(case["service_code"], documents, wanted)
        except Exception as error:  # in the app, any failure means manual entry
            failures += 1
            rows.append({"id": case["id"], "failure": f"{type(error).__name__}: {error}"})
            continue
        for key in usage:
            usage[key] += used.get(key, 0)
        checked = {c.field: c for c in check(raw, documents, wanted)}
        for field in wanted:
            label = case["labels"].get(field)
            got = checked[field]
            totals["slots"] += 1
            totals["dropped"] += got.status == "dropped"
            ok = got.value == label and type(got.value) is type(label)
            totals["correct"] += ok
            if label is not None:
                totals["present"] += 1
                totals["found"] += ok
                if got.value is not None and not ok:
                    totals["wrong_values"] += 1
            elif got.value is not None:
                totals["false_fills"] += 1
            if not ok:
                rows.append({"id": case["id"], "field": field, "label": label, "got": got.value, "status": got.status,
                             "reason": got.reason})
    result = {
        "provider": provider,
        "model": getattr(extractor, "model", None),
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cases": len(cases),
        "seconds": round(time.perf_counter() - started, 1),
        "failures": failures,
        **totals,
        "accuracy": round(totals["correct"] / totals["slots"], 3) if totals["slots"] else None,
        "recall_when_present": round(totals["found"] / totals["present"], 3) if totals["present"] else None,
        "usage": usage,
        "misses": rows,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", default="rules", choices=["rules", "claude"])
    parser.add_argument("--model")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--save", action="store_true", help="write eval/results/<provider>.json")
    args = parser.parse_args()
    result = score(args.provider, args.model, args.limit)
    summary = {k: v for k, v in result.items() if k != "misses"}
    print(json.dumps(summary, indent=1))
    if args.save:
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / f"{args.provider}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
