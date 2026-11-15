// Types and a small fetch helper for the workflow service.
// Paths start with /api, which Next.js passes on to the service (see next.config.ts).
// The session is an HttpOnly cookie, so this code never sees or stores it.

export type Role = "intake_coordinator" | "nurse_reviewer" | "medical_director" | "admin";
export type Me = { username: string; display_name: string; role: Role };
export type Risk = "on_track" | "at_risk" | "overdue" | "closed";
export type State =
  | "received"
  | "pended"
  | "ready_for_review"
  | "in_nurse_review"
  | "escalated"
  | "approved"
  | "denied"
  | "closed_no_auth"
  | "closed_ineligible"
  | "withdrawn";

export type CaseSummary = {
  id: number;
  state: State;
  priority: "standard" | "expedited";
  member: { id: string; name: string };
  provider: { npi: string; name: string };
  service: { code: string; name: string };
  received_at: string;
  due_at: string;
  risk: Risk;
  hours_left: number | null;
  rfi_count: number;
  extraction_status: string;
  assigned_to: string | null;
};

export type Fact = {
  id: number;
  field: string;
  label: string;
  value: unknown;
  quote: string | null;
  document_id: number | null;
  method: "ai" | "manual";
  status: "verified" | "dropped" | "entered";
  note: string;
};

export type Summary = {
  text: string;
  sentences: { text: string; fact_ids: number[] }[];
  method: string;
  review_status: "pending" | "accepted" | "edited";
  edited_text: string | null;
};

export type CaseDetail = CaseSummary & {
  diagnosis_codes: string[];
  service_date_start: string;
  service_date_end: string | null;
  catalogue_version: string;
  missing: { type: string; label: string }[];
  closed_reason: string | null;
  escalation_note: string | null;
  decision: null | { by: string; at: string | null; reason_code: string | null; reason: string | null; explanation: string | null };
  documents: { id: number; doc_type: string; title: string; received_at: string }[];
  submissions: { source: string; source_id: string }[];
  rfis: { items: { type: string; label: string }[]; created_at: string; resolved_at: string | null }[];
  history: { event: string; actor: string; role: string; from: State | null; to: State | null; trace_id: string; at: string }[];
  facts?: Fact[];
  summary?: Summary | null;
};

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export async function api<T>(path: string, options: { method?: "GET" | "POST"; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  // The workflow service refuses cookie requests that change something without this header.
  if (method !== "GET") headers["X-Requested-With"] = "workbench";

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError("Can't reach the workflow service. Is it running?", 0);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(errorMessage(data) ?? `Request failed with status ${response.status}`, response.status);
  }
  return data as T;
}

// FastAPI sends {"detail": "text"} for our own errors and a list when input doesn't validate.
function errorMessage(data: unknown): string | null {
  if (!data || typeof data !== "object" || !("detail" in data)) return null;
  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { loc?: unknown[]; msg?: string }) => `${String(d.loc?.at(-1) ?? "input")}: ${d.msg ?? "invalid"}`).join("; ");
  }
  return null;
}
