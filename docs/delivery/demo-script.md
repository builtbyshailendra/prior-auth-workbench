# Three-minute demo script

For recording in your own voice. Rehearse once with the system running locally:
- `docker compose up --build`
- `docker compose run --rm connectors`

Talk to the business problem first and the technology second.

| Time | Show | Say (in your own words) |
|---|---|---|
| 0:00 | The README's first paragraph | "Prior authorization at a health plan: requests come in by fax, portal, phone and X12; nurses spend their time finding facts in long packets; and since 2026 CMS requires decisions in 72 hours or 7 days. This is a working intake system for a fictional plan, on synthetic data." |
| 0:20 | Terminal: the connectors' ingest output | "Ten messages from four kinds of source systems. Watch two lines. The X12 request for the same MRI as a FHIR order linked to the existing case instead of opening a second one. The 278 with a bad NPI never left the connector; it's kept with the reason, for someone to fix." |
| 0:50 | Sign in as `ivy`: the pended sleep study | "Instead of chasing the provider one document at a time, the checklist asks for everything missing at once. When the fax arrived with the questionnaire, the case moved on by itself." |
| 1:10 | Sign in as `nina`: queue, then the lumbar case | "Sorted by deadline, not by arrival. Here are the checklist facts. Each one sits next to the exact sentence it came from. Click: there it is in the note. This one couldn't be verified: the quote wasn't in the document, so it isn't shown as a fact." |
| 1:40 | Enter the missing fact; accept the summary; escalate | "The nurse fills in what the extractor couldn't, and the summary is rebuilt from checked facts only. Nurses can approve or escalate. They can't deny." |
| 2:00 | Sign in as `dr.lee`: deny without a reason, then with one | "Only a medical director can deny, and not without a reason code: the API refuses it, and so does the database. Every step is in an audit trail nobody can edit." |
| 2:20 | GitHub Actions run: the Kubernetes job | "On every push, CI deploys to a real cluster, ships a release that crashes on startup, and checks it's rolled back without a failed call. It also stops the AI worker and checks cases still reach a nurse." |
| 2:40 | The business case table | "The measurable value comes mostly from the parts that don't need AI: no re-keying, asking once, a deadline queue. The AI is upside to be measured on a labelled test set, not assumed. That's how I'd take this to a client." |

**Don't say:**
- that it's production-ready, HIPAA-compliant, or used by a real plan
- that the AI's accuracy is known before the Claude evaluation has run
