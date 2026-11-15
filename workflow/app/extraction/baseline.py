"""A rule-based extractor: regular expressions and simple negation, no AI.

It exists to give the AI something honest to beat. It's also what CI runs end to
end, since CI has no API key. Its weaknesses are the point: it reads one sentence
at a time and is easily fooled by numbers that belong to something else.
"""
from __future__ import annotations

import re

from app.extraction.verify import NUMBER_WORDS, RawFact

NUM = r"(\d{1,2}|" + "|".join(sorted((w for w in NUMBER_WORDS if w != "no"), key=len, reverse=True)) + r")"
NEGATION = re.compile(r"\b(denies|denied|no|not|without|negative for|never)\b", re.I)


def _num(text: str) -> str:
    text = text.lower()
    return text if text.isdigit() else str(NUMBER_WORDS[text])


def sentences(documents: list[str]) -> list[str]:
    out: list[str] = []
    for doc in documents:
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", doc) if s.strip())
    return out


def _first(patterns: list[str], sents: list[str]) -> tuple[str, str] | None:
    for s in sents:
        for p in patterns:
            m = re.search(p, s, re.I)
            if m:
                return m.group(1), s
    return None


def _flag(keywords: str, sents: list[str]) -> RawFact | None:
    for s in sents:
        if re.search(keywords, s, re.I):
            return RawFact("", "false" if NEGATION.search(s) else "true", s)
    return None


class BaselineExtractor:
    provider = "rules"
    model = "regex-baseline-1"

    def extract(self, service_code: str, documents: list[str], wanted: list[str]) -> tuple[list[RawFact], dict]:
        sents = sentences(documents)
        facts: list[RawFact] = []

        def add(field: str, found):
            if found is not None:
                value, quote = found if isinstance(found, tuple) else (found.value, found.quote)
                facts.append(RawFact(field, value, quote))

        if "conservative_therapy_weeks" in wanted:
            hit = _first([
                NUM + r"\s*(?:weeks?|wks?)\s+of\s+(?:supervised\s+)?(?:physical therapy|PT|conservative)",
                r"(?:physical therapy|PT)\s*(?:x|for)\s*" + NUM + r"\s*(?:weeks?|wks?)",
                r"visits? over\s+" + NUM + r"\s*weeks?",
            ], sents)
            if hit:
                add("conservative_therapy_weeks", (_num(hit[0]), hit[1]))
            else:
                none = _first([r"(has not tried|no prior|never had) (?:any )?(physical therapy|PT)"], sents)
                if none:
                    add("conservative_therapy_weeks", ("0", none[1]))
        if "symptom_duration_weeks" in wanted:
            hit = _first([r"pain (?:for|x)\s*" + NUM + r"\s*(?:weeks?|wks?)", NUM + r"-week history"], sents)
            if hit:
                add("symptom_duration_weeks", (_num(hit[0]), hit[1]))
        if "red_flags_present" in wanted:
            add("red_flags_present", _flag(r"bowel|bladder|saddle|urinary retention|incontinence|history of cancer|fever", sents))
        if "prior_imaging_done" in wanted:
            hit = _flag(r"\b(x-ray|xray|mri|ct scan|imaging)\b", sents)
            add("prior_imaging_done", hit)
        if "epworth_score" in wanted:
            hit = _first([r"(?:epworth|ESS)\D{0,40}?(\d{1,2})\b"], sents)
            if hit:
                add("epworth_score", (hit[0], hit[1]))
        if "home_sleep_test_done" in wanted:
            add("home_sleep_test_done", _flag(r"home sleep", sents))
        if "witnessed_apneas" in wanted:
            add("witnessed_apneas", _flag(r"witnessed|pauses in (?:her |his |their )?breathing|stops breathing", sents))
        return facts, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
