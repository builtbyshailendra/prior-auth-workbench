# Product-feedback log

The friction I hit while building and testing this, written the way field feedback should reach a product team:
- **what happened,**
- **who it affects,**
- **how often,**
- **what would help.**

All observed in this project's own build and simulated pilot, not at a client.

| # | What happened | Who it affects | Seen | What would help |
|---|---|---|---|---|
| 1 | How a clearinghouse flags an expedited X12 278 depends on its companion guide, so every 278 arrives as standard until someone checks | Intake, compliance (expedited requests on a 7-day clock) | Every X12 request | Ask for the companion guide in the first integration workshop; make urgency mapping a per-clearinghouse setting |
| 2 | Whether a request for information pauses the decision clock depends on the plan's policies and contracts; the software can't guess | Compliance, the CMS metrics | Every pended case | A per-plan clock policy setting, with "never pauses" as the safe default (as built) |
| 3 | The quote check proves a sentence exists, not that it was read right. In the simulated pilot, reviewers corrected 18% of the facts the rules baseline "verified" | Nurses, AI governance | 64 of 359 verified facts | Show the quote next to every fact (done); track corrections per field; measure Claude on the negation traps before go-live |
| 4 | Reviewers want the document beside the fact, not below it | Nurses | Every review | Side-by-side document view with the quote highlighted (highlighting is done; the layout isn't) |
| 5 | Providers answer requests for information through a different channel than the original request (fax after a 278) | Intake | Common in the fixtures | Duplicate linking already attaches the documents to the open case; make it visible to the provider in status responses |
| 6 | A model-written summary would add risk without information once facts are structured | AI governance | Design time | Template summaries from checked facts (decision record 0004) |
| 7 | Next.js puts its own hidden `role="alert"` element on every page, which confused the browser tests | Engineering | Once | Test against the message text, not the role alone |
| 8 | Seeding demo data from two copies at once races, the same as table creation | Engineering, any multi-replica deployment | First Kubernetes design | Advisory locks around startup writes (done) |
