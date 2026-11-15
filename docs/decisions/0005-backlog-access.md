# 0005: Wider queue access during a declared backlog, time-boxed and logged

**Status:** agreed design, not built yet (on the roadmap)

## Context

The stakeholder map predicted this disagreement.

**Operations wants:**
- any nurse able to pick up any case when the queue backs up
- fewer clicks
- auto-routing

**IT security and compliance want:**
- least-privilege access (minimum necessary under HIPAA)
- multi-factor sign-in
- every access change through change control

The current design follows IT's position: a nurse sees unclaimed cases and their own. That's fine on a normal day, and it slows recovery from a backlog.

## Options considered

| Option | Operations | IT / compliance | Verdict |
|---|---|---|---|
| Keep strict queues always | Slow backlog recovery | Happy | Fails operations on the days that matter |
| Give every nurse every case | Fast | Fails minimum-necessary; no reason recorded for access | Rejected |
| **Backlog mode: time-boxed, declared, logged** | Fast when needed | Every widening has an owner, a reason and an expiry, and each case viewed is in the audit trail | **Chosen** |

## Decision

1. **The UM supervisor can declare a backlog for one service line,** with a reason and an end time of at most 48 hours.
2. **While it lasts,** nurses in that service line see all its open cases, not just unclaimed ones and their own.
3. **The declaration, its expiry and every case opened under it** are written to the audit trail, with the declaring supervisor's name.
4. **It ends by itself at the end time.** Extending it is a new declaration.
5. **IT security gets a weekly report** of declarations and the access made under them.
6. **What doesn't change:** decision rights (only medical directors deny) and multi-factor sign-in through the identity provider (decision record 0002).

## Consequences

- **Operations gets its speed** exactly when it's needed, without a standing exception.
- **Compliance can answer "who saw this case and why"** for every access.
- **The cost:** one more role permission (declare backlog), a small scheduler for expiry, and audit queries. It's on the roadmap after the pilot, because the pilot's queues are small.
