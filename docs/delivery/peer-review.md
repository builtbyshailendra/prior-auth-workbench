# Peer review

**Status: not done yet.** This needs a real person, and nothing here will be filled in until one has tried it. Results written by anyone else would be made up.

## Who

Someone who hasn't seen the project. Ideally a nurse, a utilization-management coordinator, or anyone who reviews documents for a living. A colleague or friend is fine. It takes about 30 minutes.

## What they do

1. Start the system (`docker compose up --build`) and send the fixtures (`docker compose run --rm connectors`).
2. Sign in as `nina`.
3. Review **three cases without looking at the facts panel.** Read the documents, find the checklist facts, then approve or escalate. Time each one.
4. Review **three different cases using the facts and the summary.** Time each one.
5. Answer the questions below.

To hide the facts panel for the first three, use cases from a run with `EXTRACTION_MODE=off`, or simply ask them not to scroll to it.

## What to record

| Case | With facts? | Minutes | Facts they found wrong | Notes |
|---|---|---|---|---|
| | No | | | |
| | No | | | |
| | No | | | |
| | Yes | | | |
| | Yes | | | |
| | Yes | | | |

## Questions

1. Did you trust the facts? What made you check one?
2. Was anything on the case page confusing or missing?
3. What would you need before using this for real work?
4. Anything that felt wrong about how decisions work (who can deny, escalation)?

## How to describe it afterwards

**"A peer review with one person, six synthetic cases"**, with the timings and quotes as recorded. Not "user research" or "validated with clinicians" unless that's what it was.
