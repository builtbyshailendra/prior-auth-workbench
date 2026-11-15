"""Fact extraction with Claude.

One request per case. Claude returns JSON in a fixed schema: for each checklist fact,
a value and the exact sentence it came from. Nothing here is trusted: the workflow
service checks every quote against the documents (app/extraction/verify.py) and drops
anything that doesn't hold up.

Design choices:
- Structured output (output_config.format with a JSON schema), so the reply always parses.
  Claude's citations feature would give quote locations too, but it can't be combined
  with structured output, so quotes are checked by our own verifier instead.
- Effort "low": this is reading and copying, not reasoning about a hard problem.
- Server-side refusal fallback on: if a safety classifier declines, the API retries on
  a fallback model in the same call. A final refusal is treated like any other failure.
- Any failure (timeout, rate limit, outage, refusal, unparseable reply) raises
  ExtractionUnavailable, and the case goes to a person. Intake never waits on this.
- Synthetic data only. A real deployment would need a HIPAA-eligible setup and a
  business associate agreement with the model provider before any PHI is sent.
"""
from __future__ import annotations

import json
import os

import anthropic

from app.extraction.fields import FIELDS
from app.extraction.verify import RawFact

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
# Prices per million tokens for the default model, from Anthropic's published rates (November 2026).
PRICE_PER_MILLION = {"claude-opus-5-5": (4.00, 20.00), "claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}

SYSTEM = """You extract facts from clinical documents for a prior-authorization review team.
The documents are synthetic test data. You never decide whether a request should be approved.

For each fact you are asked about:
- Answer only from the documents. If they don't state it, the value is "unknown".
- Copy the quote exactly from the document, as one continuous span of text, usually the
  sentence that states the fact. Don't paraphrase, shorten or join separate sentences.
- Integers: digits only, for example "6". Yes/no facts: "true" or "false".
- "False" means the documents say it's absent or wasn't done. Silence means "unknown".
- Plans and requests are not history: an MRI being requested is not prior imaging.
- When an old and a current value both appear, use the current one.

Fact definitions:
""" + "\n".join(f"- {f.name} ({f.kind}): {f.meaning}" for f in FIELDS.values())

SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": sorted(FIELDS)},
                    "value": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["field", "value", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


class ExtractionUnavailable(Exception):
    """Extraction didn't produce a usable answer. The case goes to manual entry."""


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """An upper bound: cached input is cheaper than the full input rate used here."""
    price_in, price_out = PRICE_PER_MILLION.get(model, (0.0, 0.0))
    return round(input_tokens / 1e6 * price_in + output_tokens / 1e6 * price_out, 6)


def user_message(documents: list[str], wanted: list[str]) -> str:
    docs = "\n\n".join(f'<document index="{i}">\n{text}\n</document>' for i, text in enumerate(documents))
    return f"{docs}\n\nExtract these facts: {', '.join(wanted)}. Return one entry per fact."


class ClaudeExtractor:
    provider = "claude"

    def __init__(self, model: str = MODEL, client: anthropic.Anthropic | None = None, timeout: float = 60.0):
        self.model = model
        # The SDK retries 408/409/429/5xx and connection errors twice by default.
        self.client = client or anthropic.Anthropic(timeout=timeout, max_retries=2)

    def extract(self, service_code: str, documents: list[str], wanted: list[str]) -> tuple[list[RawFact], dict]:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_message(documents, wanted)}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            )
        except anthropic.APITimeoutError as error:
            raise ExtractionUnavailable("Timed out waiting for Claude") from error
        except anthropic.RateLimitError as error:
            raise ExtractionUnavailable("Rate limited by the Claude API") from error
        except anthropic.APIStatusError as error:
            raise ExtractionUnavailable(f"Claude API answered {error.status_code}") from error
        except anthropic.APIConnectionError as error:
            raise ExtractionUnavailable("Can't reach the Claude API") from error

        if response.stop_reason == "refusal":
            raise ExtractionUnavailable("Claude declined the request")
        if response.stop_reason == "max_tokens":
            raise ExtractionUnavailable("Claude's reply was cut off")
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
        try:
            data = json.loads(text)
            facts = [RawFact(str(f["field"]), str(f["value"]), str(f["quote"])) for f in data["facts"]]
        except (ValueError, KeyError, TypeError) as error:
            raise ExtractionUnavailable("Claude's reply didn't match the expected format") from error

        usage = response.usage
        input_tokens = (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) + (
            getattr(usage, "cache_creation_input_tokens", 0) or 0)
        output_tokens = usage.output_tokens or 0
        return facts, {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd(response.model or self.model, input_tokens, output_tokens),
            "served_by": response.model,
        }
