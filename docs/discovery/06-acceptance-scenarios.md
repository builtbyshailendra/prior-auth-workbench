# 6. Acceptance scenarios

Written before the code, so the code has something to prove. Each scenario names the requirements it checks. Later steps turn each one into an automated test with the same ID, and this page will link to it.

**AS-01: a complete standard request becomes ready for review** (FR-04, FR-07, FR-08, FR-10, FR-16)
- Given a covered member and a lumbar spine MRI request with every checklist document attached
- When the request is received
- Then the case reaches "ready for review" with a 7-calendar-day clock started at receipt
- And the audit trail shows each step in order

**AS-02: missing documents are asked for all at once** (FR-08, FR-09)
- Given a sleep study request missing both the sleep questionnaire and the clinician's note
- When the request is received
- Then the case is pended, with both missing items listed in one request for information
- And when both documents arrive, the case returns to the checks and reaches "ready for review"
- And the RFI count for the case is 1

**AS-03: an expedited request runs on a 72-hour clock** (FR-10, FR-17)
- Given a request marked expedited
- When 60 hours pass without a decision
- Then the case is flagged at risk and sits at the top of the queue

**AS-04: a member not covered on the service date is closed, not denied** (FR-04)
- Given a member whose coverage ended before the requested service date
- When the request is received
- Then the case closes as "member not eligible on the service date"
- And no medical-necessity decision is recorded

**AS-05: a service that doesn't need authorization is closed with a reason** (FR-07)
- Given a service not on the authorization list
- When the request is received
- Then the case closes as "no authorization needed", recording which catalogue version said so

**AS-06: the same request from two channels opens one case** (FR-03)
- Given a request received by fax
- When the same member, provider, service and dates arrive as an X12 278 an hour later
- Then no second case is opened
- And the 278 is linked to the existing case

**AS-07: an invalid NPI is rejected with a usable reason** (FR-02, FR-05)
- Given a request whose provider NPI fails the check digit
- When it reaches the connector service
- Then it's rejected with "provider NPI check digit is invalid" and kept as a rejected record
- And after the NPI is corrected, replaying the record creates the case

**AS-08: an AI fact without a matching quote is dropped** (FR-11, NFR-04)
- Given the AI returns "conservative therapy: 8 weeks" with a quote that doesn't appear in the note
- When the extraction is checked
- Then that fact is dropped and flagged for manual entry
- And the reviewer never sees it as a confirmed fact

**AS-09: AI downtime doesn't stop intake** (FR-11, NFR-05)
- Given the AI service times out on every call
- When a complete request is received
- Then the case goes to manual fact entry and still reaches the nurse queue
- And no request is lost

**AS-10: a nurse can't deny** (FR-13, NFR-02)
- Given a nurse reviewer signed in
- When they try to deny a case through the API directly
- Then the API refuses with "forbidden"
- And the case and its audit trail are unchanged

**AS-11: a denial needs a medical director and a reason** (FR-14)
- Given a medical director signed in on an escalated case
- When they deny without a reason code
- Then the denial is refused
- And when they deny with a reason code and explanation, the case is denied and the reason is stored

**AS-12: the audit trail is complete and can't be edited** (FR-16, NFR-03)
- Given a case that has gone from received to approved
- When the audit trail is read
- Then every transition appears in order, with actor, time and trace ID
- And an attempt to update or delete an audit row fails at the database

**AS-13: a connector survives an upstream timeout** (FR-02, NFR-08)
- Given the workflow service times out on intake
- When the connector sends a request
- Then it retries with increasing waits
- And after the last attempt it parks the record with the reason
- And replaying it after the service recovers creates exactly one case

**AS-14: the CMS metrics report is correct** (FR-20)
- Given a fixed set of synthetic decided cases with known outcomes and times
- When the yearly report is produced
- Then each percentage and each average and median time matches a hand calculation
