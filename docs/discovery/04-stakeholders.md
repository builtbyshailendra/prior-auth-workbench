# 4. Stakeholders

> Fictional client, so the roles are generic. In a real engagement each row gets a name, and the "worries" column comes from talking to them, not from guessing.

## Who cares, and about what

| Stakeholder | Wants | Worries | How they'll judge the pilot |
|---|---|---|---|
| **VP Utilization Management** (sponsor) | Deadlines met, lower cost per review, clean audits | Spending money on a pilot that doesn't change the numbers | Deadline misses, cost per case, staff hours |
| **Intake supervisor** | Less re-keying and chasing | A new tool that adds steps before it removes any | Requests handled per coordinator per day; RFI rounds |
| **Nurse reviewers** | Facts laid out, cases complete when they arrive | Being blamed for an AI mistake. Losing judgment to a machine | Minutes per case; how often the summary is right |
| **Medical directors** | Only the cases that need them, with a clear summary | Denials that won't stand up on appeal | Escalation quality, reason consistency |
| **CIO / IT security** | Stable integrations, least-privilege access, change control | New system with access to PHI. Vendor and AI risk. Fragile point-to-point links | Access reviews passed, no incidents, clean change records |
| **Compliance officer** | CMS deadlines met, reasons on every denial, complete audit trail, a written AI policy | AI making or appearing to make coverage decisions | Audit sample results, timeliness reports |
| **Provider relations** | Fewer RFI calls irritating provider offices | Providers seeing more requests for information, not fewer | Provider complaints, RFI count per request |
| **Finance** | A believable return | Savings counted twice or never realized | ROI with stated assumptions, tracked after go-live |
| **Members** (indirect) | Faster decisions they can understand | Care delayed by paperwork | Decision time; clarity of reasons |

## Who decides what (RACI)

R = does it, A = signs off, C = consulted, I = kept informed.

| Decision | R | A | C | I |
|---|---|---|---|---|
| Change a service's documentation checklist | UM clinical policy lead | Lead medical director | Compliance, nurse reviewers | Intake, IT |
| Change which services need authorization | UM clinical policy lead | VP UM | Compliance, provider relations, finance | All UM staff |
| Change the AI prompt, model or thresholds | Forward deployed engineer | AI governance group (medical director, compliance, IT security) | Nurse reviewers | VP UM |
| Grant a person access to cases | IT security | UM supervisor (for their team) | Compliance | — |
| Go-live of each pilot service | Forward deployed engineer, intake supervisor | VP UM | IT, compliance, medical directors | Provider relations |
| Roll back a release | On-call engineer | IT change manager | Forward deployed engineer | VP UM |

## Known tension to plan for

**Operations wants speed. IT security wants control.**
- **Operations wants:** auto-routing, fewer clicks and broad access so anyone can pick up any case when the queue backs up.
- **IT security wants:** least-privilege access, multi-factor sign-in and every change going through change control.

Both are right. The compromise gets written down as a decision record before go-live (Step 15 of the build). The likely shape:
- Queues are opened to a wider group only during a declared backlog, with an expiry time.
- Every such grant is logged.

## Communication plan for the pilot

| What | Who | How often |
|---|---|---|
| Pilot status: deadline misses, RFIs, cases handled | Sponsor, supervisor | Weekly, 30 minutes |
| What changed this week, and what's next | All UM staff in the pilot | Weekly note |
| Decisions needed and risks | Sponsor, IT, compliance | As they arise, written |
| AI quality review: sample of extractions vs source | AI governance group | Every two weeks |
