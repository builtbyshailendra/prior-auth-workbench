# 0001: The AI gathers and drafts. People decide.

**Status:** accepted, Step 1 (before any code)

## Context

**The opportunity:** nurses spend a large share of review time finding a few facts in long clinical packets, and a language model can find and quote those facts quickly.

**The risks:**
- Models can state things that aren't in the source.
- A coverage decision affects someone's care.
- CMS's February 2024 FAQ for Medicare Advantage organizations says a medical-necessity decision must rest on the individual patient's history, physician recommendations and clinical notes. Help from an algorithm is allowed; replacing the individual review isn't.

Some products advertise automated approvals. Where that happens, it's normally a rule written and owned by the plan, such as approving any complete request from a provider with a strong approval record. That's a policy choice made by people, not a model's judgment.

## Decision

**The AI may:**
- extract the checklist facts from clinical notes, each with the exact quote it came from
- draft a reviewer summary where every statement points to a quote

**The AI may not:**
- approve, deny or pend a case for clinical reasons
- choose a denial reason
- change a case's state

**Enforced in the software:**
- The AI component has no permission to call any decision endpoint. It writes only to the extraction and summary tables.
- Every extracted fact must include a quote, and the quote must appear word for word in the note. A fact that fails the check is dropped and flagged for manual entry.
- If the AI times out, errors, returns invalid output or refuses, the case goes to manual entry. Intake never waits on the AI.
- The reviewer sees each fact next to its quote and can change it. The case records whether the summary was accepted or edited.
- Tests cover each of these. Acceptance scenarios AS-08 and AS-09, plus a test that the AI role can't reach decision endpoints.

## Consequences

- **Less automation than an "auto-approve" pitch,** and a much easier conversation with compliance, medical directors and nurses.
- **The benefit shows up as nurse minutes saved and fewer missed facts,** not as fewer nurses. The business case has to be built on that.
- **Rule-based approvals stay possible,** if the plan ever wants them, as policy-owned rules outside the AI component, reviewed like any other rule change.
