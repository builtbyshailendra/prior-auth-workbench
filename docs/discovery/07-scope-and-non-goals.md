# 7. Scope and non-goals

## In scope

- The administrative prior-authorization workflow for three outpatient services (lumbar spine MRI, in-lab sleep study, physical therapy beyond the visit limit)
- Intake from four channels: FHIR R4, an X12 278 subset, a fax index with documents, and CRM records
- Validation, documentation checklists, requests for more information, duplicate linking
- AI fact extraction with checked quotes, and a reviewer summary with a manual fallback
- Sign-in, roles and permissions; an append-only audit trail; expedited and standard deadline clocks
- Operational measures and a CMS-style metrics report
- Containers, CI, a Kubernetes deployment with a tested rollback, a runbook and a support playbook
- The discovery, delivery and business-case documents around all of it

## Not in scope, on purpose

| Not doing | Why |
|---|---|
| Making coverage or medical-necessity decisions in software | People decide. See [decision record 0001](../decisions/0001-ai-gathers-humans-decide.md) |
| Reproducing a commercial clinical criteria product | Licensed content. The sample checklists are illustrative |
| Real patient, member or provider data | Synthetic data only, everywhere |
| Pharmacy prior authorization | Drugs use NCPDP transactions and sit outside CMS-0057-F's prior-authorization provisions. See [the standards primer](08-standards-primer.md) |
| Appeals | A separate workflow. It's on the roadmap, and FR-20 reports it as "not tracked yet" |
| Claims processing and payment | Different process |
| Running a FHIR server, or conformance with the Da Vinci guides | The project reads FHIR R4 resources and borrows the CRD / DTR / PAS split, but claims no conformance |
| HIPAA compliance certification | Not possible for a portfolio project. Real deployments need a covered environment, business associate agreements, risk assessments and more |
| Mailing notices to members | Out of the pilot; the notice text itself is a "Could" (FR-21) |

## Words this project won't use about itself

"HIPAA-compliant", "Da Vinci conformant", "production-ready", "auto-approval". It can truthfully say:
- "Uses FHIR R4 resources"
- "Parses a subset of the X12 278 request"
- "Synthetic data"
- "Tested in CI"
