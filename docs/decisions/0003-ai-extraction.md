# 0003: How the AI extraction step is built

**Status:** accepted, Step 10

## Context

[Decision record 0001](0001-ai-gathers-humans-decide.md) says the AI gathers facts and people decide. This record is about how to build that so it stays true when the model is wrong, slow or down, and so IT security can sign off on it.

## Decision

1. **A separate worker process with the least privilege that works.**
   - **What it holds:** only the extractor API token.
   - **What it can do:** the workflow service lets it claim cases waiting for extraction (with their documents) and send back raw answers.
   - **What it can't do:** read queues, change a case's state or call any decision endpoint. A test calls every decision endpoint with its token and expects 403.
2. **The worker is never trusted.**
   - **The workflow service checks every answer itself** ([`verify.py`](../../workflow/app/extraction/verify.py)): the quote must appear word for word in a document, a number must appear in its quote, and values must have the right type.
   - **Anything that fails is stored as "couldn't verify",** shown to the reviewer as such, and never as a fact.
   - **The database enforces part of it:** a verified fact can't exist without a quote.
3. **Intake never waits on the AI.**
   - **A failed answer** (timeout, rate limit, outage, refusal, unparseable reply) sends the case to manual entry.
   - **A worker that never answers:** a sweep in the workflow service sends the case to manual entry after 10 minutes.
   - **Each claim is leased for 5 minutes,** so a crashed worker's cases are picked up again.
4. **The model call.**
   - **Model:** Claude Opus 5.5.
   - **One request per case,** with structured JSON output against a strict schema (the reply always parses) and effort set to low (reading and copying, not hard reasoning).
   - **Server-side refusal fallback** is on.
   - **Caching:** the instructions are marked for caching, though at today's length they're below the minimum cacheable size, so it makes no difference yet.
   - **Why no citations:** Claude's citations feature can't be combined with structured output, so our own verifier does that job.
5. **Measured, not assumed.**
   - **The labelled test set** ([`workflow/eval`](../../workflow/eval/README.md)) scores any extractor the same way.
   - **CI runs the rules baseline,** since it has no API key.
   - **A manually triggered GitHub workflow runs the Claude evaluation** when the `ANTHROPIC_API_KEY` secret exists.
6. **Cost is recorded per case,** in tokens and dollars at published prices (an upper bound, since cached input is cheaper).

## Consequences

- **The quote check catches invented sentences, not wrong readings.** A model that misreads a real sentence (for example, missing a negation) still passes it. That's why the reviewer sees each fact next to its quote, and why the test set includes negation traps.
- **The worker can run anywhere** with network access to the workflow service and the model API, and it can be scaled or stopped without touching intake.
- **For a real deployment:** PHI may only be sent to a model provider under a business associate agreement, in a HIPAA-eligible setup approved by the client's AI governance group. This project uses synthetic data only.
