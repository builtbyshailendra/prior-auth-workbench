# 0004: The summary is built from checked facts, not written by the model

**Status:** accepted, Step 11

## Context

The plan said "draft a reviewer summary where every sentence points to a quote". There were two ways to build it:

1. **Ask the model** to write a summary, then check that each sentence cites a fact.
2. **Build it by template** from the facts that already passed verification, one sentence per fact.

## Decision

Option 2.
- **By the time a summary is needed,** the facts are already structured, checked and attributed.
- **A model rewriting them adds no information,** and adds the one risk this whole design exists to prevent: a sentence that says something the facts don't.
- **Template sentences are traceable by construction.** Each carries the ID of the fact it came from, and the summary says plainly which answers couldn't be verified.

**What the reviewer can do:**
- **Accept** the summary.
- **Edit** it. The edited text is kept alongside the draft.
- **Enter or correct any fact.** The original answer is kept, marked superseded, and the summary is redrafted.

Every action is attributed and audited.

## Consequences

- **The summary reads plainly rather than fluently.** For a reviewer deciding a case, that's a feature.
- **Corrections can be counted:**
  - how often reviewers correct AI facts
  - how often they accept the summary unchanged
  - which fields get corrected most

  That's the honest measure of whether the AI is helping, and it feeds the outcome report (Step 14).
- **Choosing not to use AI where it adds risk without value** is part of the design, not a gap.
