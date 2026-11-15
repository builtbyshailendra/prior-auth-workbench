# Runbook

For whoever is on call for the pilot. Each situation lists what you'll see, what to check, and what to do. CI goes through the starred (★) situations on every push, so those steps are known to work, not just written down.

The commands assume the kind setup in `deploy/` (namespace `priorauth`). For compose, use `docker compose` with the service names `workflow`, `worker`, `web`, `postgres`.

## Deploy a release ★

```bash
deploy/scripts/deploy.sh <image tag>
```

- **Old pods keep serving** until new ones pass their readiness check (`maxUnavailable: 0`).
- **If any part isn't ready within the timeout,** the script rolls back every Deployment the release changed and exits 1.
- **CI proves it on every push** by deploying a release that crashes on startup while calling the app about five times a second.

## A release is stuck or bad ★

**You'll see:** the deploy script fails, or pods in `CrashLoopBackOff`.

**Check:**

```bash
kubectl -n priorauth get pods
kubectl -n priorauth rollout history deployment/workflow
```

**Do:** the deploy script has already rolled back. If you deployed some other way:

```bash
kubectl -n priorauth rollout undo deployment/workflow
kubectl -n priorauth rollout undo deployment/worker
kubectl -n priorauth rollout undo deployment/web
```

Then find out why from the failed pods' logs before trying again.

## The AI extraction is down or slow ★

**You'll see:**
- `priorauth_extraction_runs{status="failed"}` or `{status="timed_out"}` rising.
- Cases reaching nurses with "facts need manual entry".
- Worker logs showing `"status": "failed"`.

**This is not an outage.** Cases still reach a person: a failed answer goes to manual entry at once, and a silent worker is overtaken after `EXTRACTION_TIMEOUT_MINUTES`. Nurses take longer per case, so watch the deadline-risk metric.

**Check:**

```bash
kubectl -n priorauth logs -l app=worker --tail=50
```

Look for an expired API key, rate limits, or the model provider's status page.

**Do:**
- **For a key or provider problem:** fix it and restart the worker (`kubectl -n priorauth rollout restart deployment/worker`).
- **If it can't be fixed quickly:** switch the worker to the rules baseline (`EXTRACTOR=rules`) or scale it to zero. Both are safe.
- **Tell the UM supervisor** that facts need manual entry for now.

## The database is down ★

**You'll see:** `/api/ready` answering 503, workflow pods not ready, and the web app showing errors.

**What happens:** workflow pods stop receiving traffic but are **not restarted**, because liveness doesn't check the database. CI checks the restart count stays the same during an outage.

**Do:** bring PostgreSQL back (`kubectl -n priorauth scale statefulset/postgres --replicas=1`). Pods become ready again on their own.

**Meanwhile, connectors park what they can't deliver:** see "Messages are parked".

## Messages are parked

**You'll see:** the connector command exiting 1, and files under `out/parked/`. `node src/cli.ts status` lists them with reasons.

**Check the reason:**
- **"Can't reach the workflow service" or "Timed out":** the workflow service or the network.
- **"answered 401/403":** the connector's token is wrong or was rotated.
- **"answered 404":** the URL is wrong.

**Do:** fix the cause, then:

```bash
node src/cli.ts replay
```

Replays are safe: the workflow service treats (source, source_id) as one message.

## Messages are rejected

**You'll see:** files under `out/rejected/`, each listing what's wrong, for example "Provider NPI check digit is invalid".

**Do:**
- **Fix the data at the source.** Ask the submitter, or correct the fax index.
- **Then replay from the corrected folder:** `node src/cli.ts replay <folder>`.
- **Don't edit the rejected file** to make it pass. The source would still be wrong.

## Cases are close to their deadline

**You'll see:** `priorauth_open_cases_by_risk{risk="at_risk"}` or `{risk="overdue"}` above zero.

**Do:**
- Tell the UM supervisor.
- The queue already sorts by deadline, so the question is staffing.
- During a declared backlog, the access decision record allows widening queues temporarily (see the stakeholder map).

## Rotate a secret

The deploy script creates `priorauth-secrets` once. To rotate:
1. Edit the key in the Secret.
2. Restart the workflow, worker or web pods that use it (`kubectl rollout restart`).

Changing `session-secret` signs everyone out.
