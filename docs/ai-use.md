# Where AI is and isn't allowed

The one-page answer for compliance, medical directors and IT security. Each row says what the software does, who does it, and how that's enforced: a promise in a slide isn't a control.

| Step | Who does it | AI? | How it's enforced |
|---|---|---|---|
| Read requests from FHIR, X12, fax and CRM | Connector service | No | Deterministic adapters with tests |
| Check coverage, NPI, codes, whether authorization is needed | Workflow service | No | Rules in code and the versioned catalogue |
| Decide which documents are missing, and ask for them | Workflow service | No | The catalogue's checklist |
| Find the checklist facts in clinical notes | Extraction worker | **Yes**, or the rules baseline | The worker holds only the extractor token |
| Decide whether an extracted fact is believable | Workflow service | No | Quote must be in the document, number in the quote, typed value ([`verify.py`](../workflow/app/extraction/verify.py)); a database rule says a verified fact has a quote |
| Draft the reviewer summary | Workflow service | No | Built by template from the checked facts, one sentence per fact ([decision 0004](decisions/0004-summary-and-review.md)) |
| Enter or correct a fact | Nurse or medical director | No | Attributed and audited; the AI's answer is kept, marked superseded |
| Approve | Nurse or medical director | **Never AI** | Only human roles appear in the action table; the extractor's token gets 403 on every decision endpoint (tested) |
| Escalate | Nurse | **Never AI** | Same |
| Deny | Medical director only | **Never AI** | Same, plus a reason code and explanation required by the API and by a database constraint |
| Change the checklists or what needs authorization | Clinical policy owner | No | Reviewed change to the catalogue file; each case records the version it used |

## Why the line is drawn here

CMS's February 2024 FAQ for Medicare Advantage plans, as summarized by law firms, says a medical-necessity decision has to rest on the individual patient's history, physician recommendations and clinical notes. Help from an algorithm is allowed; replacing the individual review isn't.

Finding facts in a 40-page fax is help. Deciding is the review. See [decision record 0001](decisions/0001-ai-gathers-humans-decide.md).

## What the controls don't catch

- **The quote check proves a sentence exists, not that it was read correctly.** A model that misses a negation in a real sentence passes the check. Reviewers see each fact next to its quote for exactly this reason. The test set has negation traps, so this is measured rather than hoped away.
- **Reviewers can accept a wrong summary.** The rate of accepted versus edited summaries and corrected facts is recorded per case, so it can be watched (Step 14).

## Measuring it

| Measure | Where it comes from |
|---|---|
| Extraction accuracy and false fills | The labelled test set ([`workflow/eval`](../workflow/eval/README.md)) |
| Facts reviewers corrected | Superseded AI facts in the `facts` table |
| Summaries accepted vs edited | `summaries.review_status` |
| Cases where AI failed or timed out | `extraction_runs.status` |
| Cost per case | `extraction_runs.cost_usd` |
