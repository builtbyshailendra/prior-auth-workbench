# User acceptance test script

For the client's own staff to run before go-live, one scenario per acceptance criterion. **Not executed by a client:** this is a portfolio project. The same scenarios run as automated tests (see [traceability](traceability.md)), but UAT is people confirming the software fits their work, which tests can't do.

**Setup:** a test environment with synthetic data. `docker compose up --build`, then `docker compose run --rm connectors`. Sign in as the named demo users.

| # | Scenario | Who runs it | Steps | Expected | Pass / fail | Notes |
|---|---|---|---|---|---|---|
| UAT-01 | Complete request reaches a nurse (AS-01) | Nurse | Open the queue; open the lumbar MRI case from FHIR | Case is ready for review with a 7-day clock; facts shown with quotes | | |
| UAT-02 | Missing documents asked for at once (AS-02) | Intake | Open the pended sleep study case | Both missing items listed; after the fax arrives, the case moves to ready | | |
| UAT-03 | Expedited request runs on 72 hours (AS-03) | Supervisor | Find an expedited case | Due 72 hours after receipt; at risk in its last 12 hours | | |
| UAT-04 | Not eligible is closed, not denied (AS-04) | Intake | Open the fax for SYN-M0019 | Closed: member not covered on the date; no decision recorded | | |
| UAT-05 | No authorization needed is closed with the rule version (AS-05) | Intake | Open the CRM office visit | Closed with catalogue version shown | | |
| UAT-06 | Same request from two channels (AS-06) | Intake | Open the FHIR lumbar case | Came in by FHIR and X12; one case | | |
| UAT-07 | Bad NPI refused with a reason (AS-07) | IT / integration | Read the output of `docker compose run --rm connectors` | 278 REQ5003 refused: provider NPI check digit is invalid; never sent to the workflow service | | |
| UAT-08 | Unverifiable fact not shown as a fact (AS-08) | Nurse | Find a fact marked "Couldn't verify" | Shown as unverified with the reason; can be entered by hand | | |
| UAT-09 | AI down: cases still arrive (AS-09) | IT | Stop the worker; send a request | Case reaches the nurse queue with facts for manual entry within the timeout | | |
| UAT-10 | Nurse can't deny (AS-10) | Nurse | Pick up a case | No Deny button; escalation available | | |
| UAT-11 | Denial needs a medical director and a reason (AS-11) | Medical director | Deny an escalated case without a reason, then with one | Refused, then denied with the reason shown | | |
| UAT-12 | History is complete (AS-12) | Compliance | Open a decided case's history | Every step with who and when | | |
| UAT-13 | Connector survives an outage (AS-13) | IT | Stop the workflow service; send; restart; replay | Message parked, then delivered once | | |
| UAT-14 | CMS report adds up (AS-14) | Compliance | Admin: `/api/reports/cms?year=2026` | Percentages and times match a hand check on a sample | | |

**Sign-off:** UM supervisor, lead medical director, IT security, compliance. Name, date, and any scenarios accepted with conditions.
