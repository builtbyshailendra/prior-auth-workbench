"""Checks every extracted fact against the documents before anyone sees it.

A fact survives only if:
- its value has the right type for the field, and
- its quote appears in one of the documents (word for word, ignoring case and spacing), and
- for numbers, the number itself appears in the quote.

Anything else is dropped and flagged for a person. A model can't add a fact the
source doesn't contain, however confident it sounds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.fields import FIELDS

NUMBER_WORDS = {
    "zero": 0, "no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "eighteen": 18, "twenty": 20, "twenty-four": 24,
}


@dataclass(frozen=True)
class RawFact:
    """What an extractor returns, before checking."""

    field: str
    value: str | None  # as text: "8", "true", "false", or None for not documented
    quote: str | None


@dataclass(frozen=True)
class CheckedFact:
    field: str
    value: int | bool | None
    quote: str | None
    document_index: int | None
    status: str  # "verified", "not_documented" or "dropped"
    reason: str = ""


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_value(field: str, raw: str | None) -> tuple[bool, int | bool | None]:
    """(ok, value). A missing or "unknown" value means not documented."""
    if raw is None or normalize(raw) in ("", "unknown", "not documented", "null", "none"):
        return True, None
    spec = FIELDS[field]
    text = normalize(raw)
    if spec.kind == "boolean":
        if text in ("true", "yes"):
            return True, True
        if text in ("false", "no"):
            return True, False
        return False, None
    if re.fullmatch(r"\d{1,3}", text):
        return True, int(text)
    return False, None


NONE_DONE = re.compile(r"\b(not|never|no|none|hasn't|has not|hadn't|without)\b")


def number_in(quote: str, value: int) -> bool:
    """The number is in the quote, or it's 0 and the quote says something wasn't done."""
    text = normalize(quote)
    words = re.findall(r"[a-z]+(?:-[a-z]+)?|\d+", text)
    if any((w.isdigit() and int(w) == value) or NUMBER_WORDS.get(w) == value for w in words):
        return True
    return value == 0 and bool(NONE_DONE.search(text))


def check(facts: list[RawFact], documents: list[str], wanted: list[str]) -> list[CheckedFact]:
    """One checked fact per wanted field, in that order. Unknown fields are ignored."""
    by_field: dict[str, RawFact] = {}
    for fact in facts:
        if fact.field in wanted and fact.field not in by_field:
            by_field[fact.field] = fact
    normalized_docs = [normalize(d) for d in documents]
    checked: list[CheckedFact] = []
    for field in wanted:
        fact = by_field.get(field)
        if fact is None:
            checked.append(CheckedFact(field, None, None, None, "not_documented"))
            continue
        ok, value = parse_value(field, fact.value)
        if not ok:
            checked.append(CheckedFact(field, None, fact.quote, None, "dropped", f"Value {fact.value!r} isn't valid for this field"))
            continue
        if value is None:
            checked.append(CheckedFact(field, None, None, None, "not_documented"))
            continue
        quote = (fact.quote or "").strip()
        if len(quote) < 8:
            checked.append(CheckedFact(field, None, fact.quote, None, "dropped", "No supporting quote"))
            continue
        index = next((i for i, d in enumerate(normalized_docs) if normalize(quote) in d), None)
        if index is None:
            checked.append(CheckedFact(field, None, quote, None, "dropped", "The quote doesn't appear in any document"))
            continue
        if isinstance(value, int) and not isinstance(value, bool) and not number_in(quote, value):
            checked.append(CheckedFact(field, None, quote, index, "dropped", f"The quote doesn't contain the number {value}"))
            continue
        checked.append(CheckedFact(field, value, quote, index, "verified"))
    return checked
