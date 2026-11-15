# 1. Problem statement

> Everything in this pack is invented for a portfolio project. Tallowmere Health Plan is fictional. Every number marked **(hypothesis)** is a placeholder to check in a discovery workshop, not a measurement.

## The client

**Tallowmere Health Plan** is a regional health plan with Medicare Advantage and Medicaid managed-care members, about 380,000 people in all (hypothesis). Its utilization management (UM) team handles prior authorization: providers must get approval before certain services, and the plan has to decide within regulatory deadlines.

**The UM team (hypothesis):**
- 6 intake coordinators
- 14 nurse reviewers
- 3 part-time medical directors

## What they asked for

> "Our reviewers spend too much time collecting documents for prior-authorization requests. The information is spread across several systems, and we keep chasing providers for missing details. Help us fix the process."

## What we think is going on

These are starting hypotheses. Discovery has to confirm or kill each one.

1. **Requests arrive in four shapes.** Providers fax, use the portal, send X12 278 transactions through a clearinghouse, or phone. Coordinators re-key faxes and calls into the UM tool by hand.
   - Channel split: fax 45%, portal 35%, clearinghouse 15%, phone 5% (hypothesis).
   - Re-keying takes about 9 minutes per request (hypothesis).
2. **Many requests are incomplete.** About 40% lack a document the review needs (hypothesis). Each request for more information (RFI) adds several days and a phone call or two.
3. **Nurses hunt through long fax packets.** The packet can run to 40 pages, but the checklist needs a handful of facts: how long conservative treatment was tried, whether there are red-flag symptoms, what imaging was already done.
4. **Nobody sees deadline risk in one place.** Under the CMS Interoperability and Prior Authorization rule (CMS-0057-F), impacted payers must decide within 72 hours for expedited requests and 7 calendar days for standard ones. Today the team finds out late.
5. **Duplicates create double work.** The same request arrives by fax, then again by phone. Two cases get opened.
6. **Denial reasons are written inconsistently.** That's a compliance risk, because the rule requires a reason when a request is denied.

## What success would look like

These are proposed measures, to agree with the sponsor in the first workshop:

| Measure | Today | Target for the pilot |
|---|---|---|
| Time from receipt to "ready for a nurse" for a complete request | about 1 working day (hypothesis) | under 1 hour |
| Requests sent back for more information | about 40% (hypothesis) | under 25%, by asking for everything missing at once |
| Nurse time per case, spent finding facts | about 15 minutes (hypothesis) | under 5 minutes, with facts and quotes laid out |
| Requests that miss the 72-hour or 7-day deadline | unknown | measured daily, then driven down |
| Duplicate cases opened | unknown | duplicates linked, not reopened |

## What doesn't change

- **People make every coverage decision.** Nurses approve or escalate; medical directors approve or deny. The software gathers, checks and lays out information; it doesn't decide.
- **The clinical criteria stay the plan's own.** This project doesn't reproduce any commercial criteria product, and its sample checklists are labelled illustrative.

## Pilot scope

Three outpatient services, chosen because they're high volume and their documentation rules are fairly clear:

| Service | Example code | Why |
|---|---|---|
| Lumbar spine MRI | CPT 72148 | High volume. A common reason for missing documents (conservative treatment) |
| Sleep study in a lab | CPT 95810 | Clear documentation needs. Often sent back for a missing sleep questionnaire |
| Physical therapy beyond the plan's visit limit | CPT 97110 | Repeat requests. Good test for duplicate handling |

Code numbers are used only as identifiers. Descriptions are written in plain words for this project.
