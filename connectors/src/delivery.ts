// Sends one request to the workflow service, retrying what's worth retrying.
//
// Retried: network errors, timeouts, 408, 429, 500, 502, 503, 504, with exponential
// backoff plus jitter, honouring Retry-After. After the last attempt the record is
// "parked" with its reason, never dropped.
// Not retried: 422 (the request itself is wrong: "rejected", a person must fix it),
// 401/403/404 (the connector is misconfigured: "parked" at once, retrying won't help).
// Replays are safe because the workflow service treats (source, source_id) as one message.

import type { IntakeRequest, Problem } from "./canonical.ts";

export type DeliveryOptions = {
  baseUrl: string;
  token: string;
  traceId: string;
  fetchImpl?: typeof fetch;
  maxAttempts?: number;
  timeoutMs?: number;
  baseDelayMs?: number;
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
};

export type DeliveryResult =
  | { status: "delivered"; outcome: string; caseId: number; state: string; attempts: number }
  | { status: "rejected"; reason: string; problems: Problem[]; attempts: number }
  | { status: "parked"; reason: string; attempts: number };

const RETRYABLE = new Set([408, 429, 500, 502, 503, 504]);
const MAX_DELAY_MS = 30_000;

export function backoff(attempt: number, baseDelayMs: number, random: () => number, retryAfterSeconds?: number): number {
  const exponential = Math.min(baseDelayMs * 2 ** (attempt - 1), MAX_DELAY_MS);
  const jittered = exponential + Math.floor(random() * (baseDelayMs / 2));
  if (retryAfterSeconds !== undefined && Number.isFinite(retryAfterSeconds)) {
    return Math.min(Math.max(jittered, retryAfterSeconds * 1000), MAX_DELAY_MS);
  }
  return jittered;
}

export async function deliver(request: IntakeRequest, options: DeliveryOptions): Promise<DeliveryResult> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const maxAttempts = options.maxAttempts ?? 4;
  const timeoutMs = options.timeoutMs ?? 5_000;
  const baseDelayMs = options.baseDelayMs ?? 500;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const random = options.random ?? Math.random;

  let lastReason = "";
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    let response: Response;
    try {
      response = await fetchImpl(`${options.baseUrl}/api/intake`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${options.token}`,
          "X-Trace-Id": options.traceId,
        },
        body: JSON.stringify(request),
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      const name = (error as Error).name;
      lastReason = name === "TimeoutError" ? `Timed out after ${timeoutMs} ms` : `Can't reach the workflow service (${(error as Error).message})`;
      if (attempt < maxAttempts) await sleep(backoff(attempt, baseDelayMs, random));
      continue;
    }

    const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    if (response.status === 200 || response.status === 201) {
      return { status: "delivered", outcome: String(body.outcome), caseId: Number(body.case_id), state: String(body.state), attempts: attempt };
    }
    if (response.status === 422) {
      const problems = Array.isArray(body.problems)
        ? (body.problems as { field: string; message: string }[]).map((p) => ({ field: p.field, message: p.message }))
        : [];
      return { status: "rejected", reason: String(body.detail ?? "Rejected by the workflow service"), problems, attempts: attempt };
    }
    if (response.status === 401 || response.status === 403 || response.status === 404) {
      return { status: "parked", reason: `Workflow service answered ${response.status}: check the URL and API token`, attempts: attempt };
    }
    if (!RETRYABLE.has(response.status)) {
      return { status: "rejected", reason: `Workflow service answered ${response.status}`, problems: [], attempts: attempt };
    }
    lastReason = `Workflow service answered ${response.status}`;
    const retryAfter = response.headers.get("retry-after");
    if (attempt < maxAttempts) await sleep(backoff(attempt, baseDelayMs, random, retryAfter ? Number(retryAfter) : undefined));
  }
  return { status: "parked", reason: `${lastReason}; gave up after ${maxAttempts} attempts`, attempts: maxAttempts };
}
