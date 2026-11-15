import type { Risk, Role, State } from "./api";

export const STATE_LABEL: Record<State, string> = {
  received: "Received",
  pended: "Waiting for documents",
  ready_for_review: "Ready for review",
  in_nurse_review: "In nurse review",
  escalated: "With medical director",
  approved: "Approved",
  denied: "Denied",
  closed_no_auth: "No authorization needed",
  closed_ineligible: "Member not eligible",
  withdrawn: "Withdrawn",
};

export const RISK_LABEL: Record<Risk, string> = {
  on_track: "On track",
  at_risk: "At risk",
  overdue: "Overdue",
  closed: "Closed",
};

export const ROLE_LABEL: Record<Role, string> = {
  intake_coordinator: "Intake coordinator",
  nurse_reviewer: "Nurse reviewer",
  medical_director: "Medical director",
  admin: "Admin",
};

export const EVENT_LABEL: Record<string, string> = {
  received: "received the request",
  ready_for_review: "marked it ready for review",
  pended: "asked the provider for missing documents",
  documents_received: "received documents",
  rechecked: "re-ran the checks",
  duplicate_linked: "linked a duplicate submission",
  closed_no_auth: "closed it: no authorization needed",
  closed_ineligible: "closed it: member not eligible",
  start_review: "picked it up for review",
  approve: "approved it",
  escalate: "escalated it to a medical director",
  deny: "denied it",
  withdraw: "withdrew it",
  awaiting_extraction: "queued it for fact extraction",
  facts_extracted: "extracted facts",
  extraction_timed_out: "gave up waiting for extraction; manual entry needed",
  extraction_failed: "couldn't extract facts; manual entry needed",
  fact_entered: "entered a fact",
  summary_drafted: "drafted a summary",
  summary_reviewed: "reviewed the summary",
};

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function hoursLeftText(hours: number | null): string {
  if (hours === null) return "";
  if (hours <= 0) return `${Math.abs(hours)} h overdue`;
  if (hours < 48) return `${hours} h left`;
  return `${Math.floor(hours / 24)} d ${Math.round(hours % 24)} h left`;
}
