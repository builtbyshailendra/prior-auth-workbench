# 8. Standards primer: what each standard is for

A one-page map of the healthcare standards a prior-authorization project runs into, and how deep this project goes into each. **Know the purpose of all of them; implement one narrow piece properly before expanding.**

| Standard | What it is | Where it shows up in prior authorization | In this project |
|---|---|---|---|
| **HL7 FHIR R4** (4.0.1) | A REST API style plus a library of "resources" (Patient, Coverage, ServiceRequest, DocumentReference, Claim, ...) exchanged as JSON | Pulling clinical context from EHRs; the newer API route for submitting requests | Step 6 reads a FHIR R4 bundle (Patient, Coverage, ServiceRequest, DocumentReference) and maps it into the internal request. No FHIR server |
| **Da Vinci CRD** | FHIR guide: "Does this service need authorization, and what's needed?" asked from inside the EHR, using CDS Hooks | Before the order is finished | The same question, answered by the service catalogue in Step 2 |
| **Da Vinci DTR** | FHIR guide: collect the documentation the payer needs, using Questionnaires and rules | Gathering documents | The same idea as the documentation checklist (Steps 2–3) |
| **Da Vinci PAS** | FHIR guide for submitting the request and getting the answer, a Claim with use "preauthorization", and mapping to and from X12 278 | Submission and response | The internal request plays the role of the PAS submission. Not conformant |
| **X12 278** (005010X217) | The HIPAA-named EDI transaction for health care services review: request and response | Clearinghouse submissions, still the most common electronic route | Step 7 parses the parts of the 278 request the app needs. Fixtures are hand-built synthetic files |
| **X12 275** | EDI transaction for sending additional documentation | Attachments following a 278 | Not implemented. Documents arrive with the fax index instead |
| **NCPDP SCRIPT** | Pharmacy standard for e-prescribing, including electronic prior authorization for drugs | Drug prior authorization | Out of scope. Drugs sit outside CMS-0057-F's prior-authorization provisions |
| **C-CDA** | XML clinical documents built on HL7 CDA R2 (Continuity of Care Document, progress notes, discharge summaries) | How many EHRs send clinical notes | Out of scope for now. Notes arrive as plain text. Parsing C-CDA is a possible later step |

## The regulation the project is designed around

**CMS Interoperability and Prior Authorization Final Rule (CMS-0057-F)**, published January 2024.

**Who it applies to:** Medicare Advantage organizations, Medicaid and CHIP programs (fee-for-service and managed care), and qualified health plan issuers on the federal exchanges.

**Decision deadlines** (from January 2026):
- 72 hours for expedited requests
- 7 calendar days for standard requests
- QHP issuers on the federal exchanges are excluded from the deadline requirement.

**Denial reasons:** a specific reason must be given when a request is denied.

**Public metrics,** posted on the payer's website every year by 31 March for the previous calendar year (first due 31 March 2026). The list includes:
- the services that need authorization
- percent approved, percent denied, percent approved after appeal
- average and median decision times for standard and expedited requests

Drugs are excluded.

**Prior Authorization API** (from January 2027): a FHIR API that:
- lists covered items and services needing authorization
- states documentation requirements
- returns approve / deny / more information needed

CMS has allowed implementers to skip translating the FHIR request into or out of X12 278 (per the PAS guide).

**This project uses it for:**
- the 72-hour and 7-day clocks (FR-10)
- reasons on every denial (FR-14)
- the metrics report (FR-20)

## AI in coverage decisions

CMS's February 2024 FAQ for Medicare Advantage organizations, as summarized by law firms:
- Plans may use algorithms and AI to help.
- A medical-necessity decision must rest on the individual patient's history, physician recommendations and clinical notes, not on a prediction from a larger dataset.

This project goes further: the AI gathers and summarizes, and people decide. See [decision record 0001](../decisions/0001-ai-gathers-humans-decide.md).

## Synthetic data sources

- **Synthea:** MITRE's open-source synthetic patient generator, which outputs FHIR R4. Good for realistic patients and coverage.
- **Clinical notes and X12 files** are hand-written for this project and labelled fiction.

## Sources

- [HL7 FHIR overview](https://hl7.org/fhir/overview.html)
- [Da Vinci PAS](https://hl7.org/fhir/us/davinci-pas/en/)
- [Da Vinci CRD](https://build.fhir.org/ig/HL7/davinci-crd/en/)
- [X12 healthcare transaction flow](https://x12.org/flow/health-care)
- [NCPDP e-prescribing resources](https://www.ncpdp.org/Resources/ePrescribing-Industry-Information)
- [C-CDA guide](https://hl7.org/cda/us/ccda/)
- [CMS-0057-F fact sheet](https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f)
- [ASHA summary of CMS-0057-F](https://www.asha.org/news/2024/cms-finalizes-a-new-prior-authorization-and-health-information-exchange-rule/)
- [Health Samurai: CMS-0057-F public reporting](https://www.health-samurai.io/docs/payerbox/compliance/reporting)
- [Norton Rose Fulbright on the CMS AI FAQ](https://nortonrosefulbright.com/en-ug/knowledge/publications/644bd9a2/cms-clarifies-medicare-advantage-organizations-use-of-ai-and-algorithms-in-coverage-decisions)
- [DLA Piper on the CMS FAQ](https://www.dlapiper.com/en-ae/insights/publications/2024/02/cms-issues-faq-to-medicare-advantage-organizations)
