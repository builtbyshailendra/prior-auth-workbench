# Deployment pattern: reusable notes for the next engagement

What worked here and would carry to another prior-authorization deployment, or to any "AI-assisted intake with human decisions" workflow.

| Pattern | What it is here | Why it carries over |
|---|---|---|
| **Rules as versioned data** | `workflow/rules/catalogue.yaml`; each case records the version it was checked against | Clinical policy changes without a code release, and every decision can be traced to the rules in force |
| **One internal request format** | `connectors/src/canonical.ts` mirrors `workflow/app/schemas.py` | New source systems need an adapter, not a workflow change |
| **Idempotent intake** | (source, source_id) is one message; replays are harmless | Retries and replays stop being dangerous, so connectors can retry freely |
| **Business-level duplicate linking** | Same member + provider + service + date links to the open case; enforced by a lock and a partial unique index | Different channels for the same request is the normal case in healthcare |
| **Outbox for failures** | Parked (delivery problem) vs rejected (data problem), originals kept, replay command | Nothing is lost, and the two kinds of failure go to different people |
| **Least-privilege AI worker** | A separate process holding only the extractor token | IT security can review one narrow permission instead of "the AI" |
| **Never trust the model's output** | Quotes checked against the source; numbers checked in their quote; unverified answers shown as such | Works with any model or provider |
| **AI failure ≠ outage** | Failed or silent extraction sends the case to manual entry | The service level doesn't depend on a third-party model |
| **People decide, enforced in code** | Action table with human roles only; reason codes required; database constraints | Compliance can read the control, not just the policy |
| **Labelled test set before the model** | `workflow/eval`, with traps and false fills counted separately | The accuracy claim comes from measurement, and comparing models is a command |
| **Tested rollback** | Deploy script rolls back the whole release; CI deploys a broken one on every push | "We can roll back" is proven, not assumed |
| **Probes that don't cascade** | Liveness doesn't check the database; readiness does | A database outage doesn't become a restart storm |

## What would change for a real client

- **Identity:** OIDC or SAML to the client's identity provider instead of passwords (see decision record 0002).
- **Data:**
  - a managed PostgreSQL with backups and point-in-time recovery
  - documents in the client's document store, referenced, not copied
- **Eligibility:** a live lookup in the core admin system (or a near-real-time replica) instead of the seeded member list.
- **Model access:** a HIPAA-eligible setup with a business associate agreement, approved by the client's AI governance group.
- **Integrations:**
  - X12 through the client's clearinghouse, with its companion guide
  - FHIR through the provider groups' endpoints with SMART backend auth
- **Monitoring:** Prometheus and alerting in the client's stack. The `/metrics` endpoint already exposes what the runbook alerts on.
