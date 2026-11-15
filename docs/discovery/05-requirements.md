# 5. Requirements

Each requirement has an ID that acceptance scenarios and tests refer to, and the build step that delivers it. **Must** is needed for the pilot, **Should** strongly wanted, **Could** if time allows.

## Functional

| ID | Requirement | Priority | Step |
|---|---|---|---|
| FR-01 | Accept requests from four channels and turn each into one internal request format: a FHIR R4 bundle (EHR), an X12 278 request (clearinghouse), a fax index row with its document (legacy), and a CRM record (portal/phone) | Must | 6–7 |
| FR-02 | Reject malformed input with a reason a person can act on. Keep the rejected record and allow it to be replayed once fixed | Must | 8 |
| FR-03 | Recognize a duplicate (same member, provider, service and dates, from any channel) and link it to the existing case instead of opening a new one | Must | 3, 8 |
| FR-04 | Check that the member's coverage is active on the requested service date | Must | 2 |
| FR-05 | Check the provider NPI: 10 digits with a valid check digit | Must | 2 |
| FR-06 | Check code formats: CPT/HCPCS for the service, ICD-10-CM for diagnoses | Must | 2 |
| FR-07 | Look up whether the service needs authorization. If not, close the case as "no authorization needed" and record why | Must | 2–3 |
| FR-08 | Compare the documents received against the service's documentation checklist and list exactly what's missing | Must | 2–3 |
| FR-09 | Pend a case for more information with the full list of missing items, reopen it when documents arrive, and count RFI rounds | Must | 3 |
| FR-10 | Mark each request expedited or standard. Start its clock at receipt (72 hours or 7 calendar days) and flag cases at risk of missing it | Must | 3 |
| FR-11 | Extract the checklist facts from clinical notes, each with the quote it came from. Check every quote really appears in the note. Send the case to manual entry when extraction fails | Must | 10 |
| FR-12 | Draft a reviewer summary where each statement points to a quote. Record whether the reviewer accepted or edited it | Should | 11 |
| FR-13 | A nurse reviewer can approve or escalate a case, but cannot deny one | Must | 4 |
| FR-14 | A medical director can approve or deny. A denial can't be saved without a reason code and an explanation | Must | 4 |
| FR-15 | Reviewers see only the cases in their own queue. Admins manage users and settings but can't decide cases | Must | 4 |
| FR-16 | Record every state change and decision in an append-only audit trail: who, when, from which state to which, and a trace ID | Must | 3 |
| FR-17 | Show a queue sorted by deadline risk, filterable by service, state and priority | Must | 5 |
| FR-18 | Show a case page with its documents, extracted facts with highlighted quotes, RFIs and full history | Must | 5, 11 |
| FR-19 | Report operational measures: time to ready-for-review, pend rate, extraction accuracy and acceptance, cases at risk | Should | 12, 14 |
| FR-20 | Produce the prior-authorization metrics CMS-0057-F requires payers to publish yearly, including the list of services needing authorization, percent approved, percent denied, percent approved after appeal, and average and median decision times for standard and expedited requests. Appeals are outside the pilot, so that metric reads "not tracked yet" | Should | 14 |
| FR-21 | Generate the decision notice text from the structured decision and reason | Could | 15 |

## Non-functional

| ID | Requirement | Priority | Step |
|---|---|---|---|
| NFR-01 | Synthetic data only. All fixtures use reserved synthetic identifiers. No real patient, member or provider data, ever | Must | all |
| NFR-02 | Only signed-in users can use the app. Role permissions are enforced by the API, not just hidden in the screen | Must | 4 |
| NFR-03 | The application's database user can't update or delete audit records | Must | 3 |
| NFR-04 | The AI never makes a coverage decision. Enforced in code and covered by tests | Must | 10–11 |
| NFR-05 | An AI failure (timeout, error, invalid output, refusal) never blocks intake. The case continues through manual entry | Must | 10 |
| NFR-06 | AI tokens and cost are recorded per case | Should | 10 |
| NFR-07 | One trace ID follows a request from the source message to the decision, across services and logs | Must | 12 |
| NFR-08 | No request is lost when a downstream service is down. Connectors retry with backoff, then park the record with its reason | Must | 8 |
| NFR-09 | One command starts the whole stack locally. CI runs on every push. Rollback is documented and tested | Must | 12–13 |
| NFR-10 | A complete request reaches "ready for review" within 60 seconds, excluding human time, in the test environment (illustrative target) | Should | 14 |
| NFR-11 | Health and readiness endpoints, metrics and structured logs on every service | Must | 12 |
| NFR-12 | Logs carry IDs, not note text or member names (minimum necessary) | Must | 3, 12 |

## Open questions for the client

These go to the first workshop. The answers would change the design.

1. **Real volumes.** What are the actual volumes per channel and per service, and how do they vary by week?
2. **Where the checklists live.** Are the documentation checklists written down, or in reviewers' heads? Who owns them?
3. **Licensed criteria.** Does the plan license a clinical criteria product? This project won't reproduce one, but the workflow has to leave room for it.
4. **Eligibility access.** What can a new system read from the core admin system: an API, a read replica or a nightly file? How fresh is coverage data?
5. **Clocks.** Which events start and stop the clock today? Does an RFI pause it under the plan's own policies and contracts?
6. **AI policy.** Who must approve AI use on PHI, and is there a policy already? Which vendors have a business associate agreement?
7. **Notices.** How are decision notices sent to providers and members today, and who signs off on letter wording?
8. **Retention.** How long must documents and audit records be kept, and where?
9. **Identity.** Which identity provider should staff sign in with (single sign-on), and how are joiners and leavers handled?
10. **Pilot scope.** Is the pilot allowed to change how work reaches nurses, or only the tools they use?
