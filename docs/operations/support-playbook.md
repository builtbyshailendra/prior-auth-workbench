# Support playbook

For the first weeks after go-live: who answers what, how fast, and the questions users actually ask. Written before go-live, then corrected from real tickets.

## Who answers what

| Level | Who | Handles | Hands on when |
|---|---|---|---|
| 1 | UM supervisor / super-user in each team | "How do I…", sign-in problems, a case in the wrong queue | It looks like a fault, or affects more than one person |
| 2 | Forward deployed engineer (pilot) | Faults, wrong facts, connector rejections, deadline-risk alerts | It needs a code change or infrastructure work |
| 3 | Platform / IT | Database, cluster, identity provider, network | — |

## Response targets during the pilot

| Situation | Respond in | Why |
|---|---|---|
| Expedited cases can't be worked | 30 minutes | 72-hour clock |
| Any case type can't be worked | 2 hours | 7-day clock |
| Wrong or missing fact on one case | Same working day | The reviewer can enter it by hand meanwhile |
| How-to question | Next working day | — |

## Questions users ask, with answers

**"The AI said 6 weeks of therapy, but the note says 4."**
1. Open the fact and click **Show in document**.
2. If the quote is real but was misread, choose **Correct**, enter 4, and say where it is in the documents.

Corrections are counted, so this feeds the accuracy review. Raise it with the forward deployed engineer if it happens repeatedly for the same kind of note.

**"A fact says Couldn't verify."** The model gave an answer whose quote wasn't in the documents, so it's not shown as a fact. Read the documents and enter the fact yourself.

**"Facts need manual entry on every case today."** Extraction is down or switched off. Cases still arrive, and you enter the facts. Check the status message from the pilot team.

**"I can't see a case my colleague mentioned."**
- **Nurses** see unclaimed cases and their own.
- **Medical directors** see escalated cases and the ones they decided.

That's deliberate (minimum necessary). Ask the supervisor to reassign it if needed.

**"I need to deny but there's no Deny button."** Only medical directors deny. Escalate it with a note saying what's unclear.

**"The provider says they sent the documents, but the case is still waiting."**
- Check the case history for "received documents".
- If nothing arrived, check the connectors' rejected and parked lists for that provider.
- A fax index row pointing at a missing file is rejected with that reason.

**"Two cases for the same request."** They shouldn't exist: duplicates from any channel are linked to the open case. If you see two open ones, it's a fault. Send both case numbers to level 2.

## What to collect in a ticket

- Case number and the time
- What you expected and what happened
- The trace ID if an error showed one. Every API response carries `X-Trace-Id`, and it follows the request through the logs.
- **No patient details in the ticket.** The case number is enough.

## Weekly during the pilot

Review with the UM supervisor:
- tickets by type
- facts corrected by reviewers, and which fields
- summaries accepted vs edited
- extraction failures
- cases that went at-risk

Turn the top friction points into the product-feedback log ([`docs/delivery/product-feedback.md`](../delivery/product-feedback.md)).
