# Business case

For the VP of Utilization Management at the fictional Tallowmere Health Plan. **Every number is a hypothesis to replace with the plan's own data.** The calculator ([`roi.py`](roi.py)) keeps them all in one place, and it refuses hypotheses that don't fit the team's headcount.

## The decision

Run a 12-week pilot of digital intake, checklist-driven requests for information, a deadline-sorted queue and checked AI fact extraction, on three outpatient services.

## Why now

- **CMS-0057-F deadlines** (72 hours expedited, 7 days standard) apply from 2026.
- **The yearly public metrics** (approval and denial rates, decision times) are published under the plan's name.
- **The Prior Authorization API** is due in January 2027. A clean internal workflow is the foundation for it.

## Where the value comes from

| Lever | What changes | AI needed? | Confidence |
|---|---|---|---|
| No more re-keying | Connectors turn fax index rows, portal and phone records, X12 and FHIR into cases | No | High: deterministic, tested |
| Fewer request-for-information rounds | Everything missing is asked for at once | No | High, once the checklists are written down |
| Fewer missed deadlines | Queue sorted by time left; at-risk alerts | No | High |
| Faster fact-finding for nurses | Facts laid out with their quotes | **Yes** | **Unknown until Claude is measured.** The rules baseline saves little |
| Consistent denial reasons | Reason codes required | No | High |

**The finding that matters:** most of the measurable value comes from the parts that don't need AI. In the calculator, coordinator time freed from re-keying and document chasing is about 6,450 hours a year in every scenario. The AI scenarios only change the nurse line. The pilot pays for itself on the quick wins. The AI is upside to be proven, not the foundation of the case.

## Scenarios

`python docs/delivery/roi.py`, all inputs hypotheses:

| Scenario | Nurse minutes saved per case | Coordinator hours freed / year | Nurse hours freed / year | Net / year | Payback |
|---|---|---|---|---|---|
| Low: rules-level accuracy, reviewers re-check everything | 2 | 6,453 | 1,333 | $224,907 | 9.6 months |
| Expected: most facts right, quotes speed up checking | 6 | 6,453 | 4,000 | $384,907 | 5.6 months |
| High: facts rarely corrected | 9 | 6,453 | 6,000 | $504,907 | 4.3 months |

**Sanity check built into the calculator:** today's re-keying and document chasing take 88% of the coordinators' hours (the team is stretched, which matches the problem statement), and finding facts takes 40% of the nurses'.

**"Hours freed" is capacity, not headcount.** The aim is deadlines met and nurses on judgment instead of paperwork. Counting it as savings needs the sponsor and finance to agree how the capacity is used.

## What must be true

1. **The checklists for the three pilot services get written down** and signed off by the lead medical director. Without them, neither the RFI lever nor the extraction works.
2. **IT can give the connectors access** to the fax index, the portal/CRM export and the clearinghouse feed.
3. **The AI governance group approves** the extraction design (decision record 0003) and a model provider under a business associate agreement. Until then, the pilot runs with extraction off and still delivers the non-AI levers.
4. **The rules-or-Claude decision is made on the labelled test set,** not on a demo.

## Risks

| Risk | Mitigation |
|---|---|
| AI reads a real sentence wrongly | Facts shown with quotes; reviewers correct; correction rate tracked weekly; negation traps in the test set |
| Model outage | Failure goes to manual entry; the runbook drill runs on every push |
| Providers don't answer requests faster | Measure RFI rounds and turnaround per provider; provider relations follows up with the slowest |
| Nurses don't trust the facts | Peer review before go-live; the summary is plain and traceable; decisions stay with nurses |
| Savings counted but never realized | Report capacity freed, deadline misses and RFI rounds weekly against the baseline |

## How we'll know (measured weekly from the system's own reports)

- **Time from receipt to the nurse queue,** and to a decision, by priority.
- **Deadline misses,** expedited and standard.
- **Request-for-information rounds per case.**
- **Facts corrected by reviewers,** and summaries accepted unchanged.
- **Extraction failures, and cost per case.**
