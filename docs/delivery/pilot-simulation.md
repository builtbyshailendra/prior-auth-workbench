# Simulated pilot: 200 requests

Run on 15 November 2026 with [`workflow/sim/pilot.py`](../../workflow/sim/pilot.py) against a real running workflow service and PostgreSQL. Raw results: [`pilot-simulation.json`](pilot-simulation.json).

**Read this first.** This is a test environment with synthetic data and simulated people. Some numbers below are measurements of the software; others are inputs the script chose. Each table says which.

## What was real and what was simulated

| Part | Real or simulated |
|---|---|
| Workflow service, database, checks, audit timestamps, reports | **Real** |
| Extraction worker's code | **Real**, run in-process with the rules baseline (no API key yet) |
| 200 requests: services, channels, missing documents, bad NPIs, ineligible members | **Synthetic**, mix chosen by the script |
| Clinical notes | **Synthetic**, from the labelled-note generator, so the right answers are known |
| Requests sent through the connector adapters | **No**: sent in the internal format the connectors produce. The adapters are tested separately, and CI sends every fixture through them |
| Receipt times | **Simulated**: back-dated by the script |
| Nurses and the medical director | **Simulated**: code that corrects facts against the known answers and decides by an illustrative policy, not medical policy |

## Measured: the software

| Measure | Result | Notes |
|---|---|---|
| Intake to nurse queue (cases with no missing documents) | median **6.0 s**, 95th percentile 10.1 s, max 11.2 s | Includes waiting for extraction. The script sent all 200 requests first, then ran the worker, so this is an upper bound for this setup. Target (NFR-10): under 60 s |
| Requests refused at intake | 11 of 200 | Bad NPI check digits (the script made about 3%) plus other format problems; refused with reasons, nothing stored |
| Duplicates linked instead of opened | 1 | Two random requests happened to match member, provider, service and date |
| Extraction runs | 139 ok, 0 failed | Rules baseline, in-process |
| Facts the extractor verified that reviewers kept | **295** | Correct against the known answers |
| Verified facts reviewers had to correct | **64** (18% of verified facts) | The baseline's wrong readings: negations, plan-only MRIs, old scores. The quote was real, the reading wrong |
| Facts reviewers had to fill in | 61 | Not found, or found but couldn't be verified |
| Summaries accepted unchanged | 63 of 139 (**45%**) | The rest were edited because a fact was corrected |

**What this says:**
- **The software side is fast enough.** Seconds from intake to the nurse queue.
- **The rules baseline isn't good enough to save much reviewer work.** One in five facts it verifies is wrong, so a reviewer still has to check everything. It's the same story the labelled test set tells (75.9% correct).
- **The open question is the model.** Whether Claude Opus 5.5 does better is exactly what the [Claude evaluation](../../workflow/eval/README.md) will answer once there's an API key. Until then, nobody should claim time savings.

## Set by the script: not results

| Report line | Value | Why it isn't evidence |
|---|---|---|
| Request-for-information rate | 30.6% | The script held back a document from 30% of requests |
| Providers who answered | 42 | The script made 80% of them answer |
| Percent approved / denied | 80.2% / 19.8% | The simulated reviewers' illustrative policy |
| Decision time, standard | average 79.8 h, median 75.0 h | Receipt times back-dated by the script |
| Decision time, expedited | average 34.6 h, median 30.5 h | Same |

These lines show that the CMS-style report computes correctly on a few hundred cases; the numbers themselves come from the script. The report's arithmetic is checked against a hand calculation in a test (AS-14).

## Not measured yet

- **Real reviewer time per case,** with and without the facts and summary. That needs a person: see [peer review](peer-review.md).
- **Claude's accuracy and cost** on the test set: needs an API key.

## Run it yourself

```bash
# a fresh database and a workflow service in worker mode
createdb -h 127.0.0.1 -p 5433 -U postgres priorauth_sim
cd workflow
DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/priorauth_sim EXTRACTION_MODE=worker \
  CONNECTOR_TOKEN=local-connector-token-0123456789 EXTRACTOR_TOKEN=local-extractor-token-0123456789 \
  python -m uvicorn app.main:app --port 8011 &
CONNECTOR_TOKEN=local-connector-token-0123456789 EXTRACTOR_TOKEN=local-extractor-token-0123456789 \
  python -m sim.pilot --url http://127.0.0.1:8011 --requests 200
```
