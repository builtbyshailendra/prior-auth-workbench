// Sends one request to the workflow service.

import type { IntakeRequest, Problem } from "./canonical.ts";

export type DeliveryOptions = {
  baseUrl: string;
  token: string;
  traceId: string;
  fetchImpl?: typeof fetch;
};

export type DeliveryResult =
  | { status: "delivered"; outcome: string; caseId: number; state: string; attempts: number }
  | { status: "rejected"; reason: string; problems: Problem[]; attempts: number }
  | { status: "failed"; reason: string; attempts: number };

export async function deliver(request: IntakeRequest, options: DeliveryOptions): Promise<DeliveryResult> {
  const fetchImpl = options.fetchImpl ?? fetch;
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
    });
  } catch (error) {
    return { status: "failed", reason: `Can't reach the workflow service: ${(error as Error).message}`, attempts: 1 };
  }
  const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (response.status === 200 || response.status === 201) {
    return { status: "delivered", outcome: String(body.outcome), caseId: Number(body.case_id), state: String(body.state), attempts: 1 };
  }
  if (response.status === 422) {
    const problems = Array.isArray(body.problems)
      ? (body.problems as { field: string; message: string }[]).map((p) => ({ field: p.field, message: p.message }))
      : [];
    return { status: "rejected", reason: String(body.detail ?? "Rejected by the workflow service"), problems, attempts: 1 };
  }
  return { status: "failed", reason: `Workflow service answered ${response.status}`, attempts: 1 };
}
