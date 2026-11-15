// CRM case record (portal form or phone call logged by the call center) -> internal request.

import { AdapterError, type IntakeRequest, type Problem } from "../canonical.ts";

export type CrmCase = {
  case_number?: string;
  created?: string;
  channel?: string;
  member?: { id?: string; name?: string };
  provider?: { npi?: string; name?: string };
  request?: { cpt?: string; icd10?: string[]; date?: string; urgent?: boolean };
  attachments?: { type?: string; title?: string; text?: string }[];
};

export function fromCrm(record: CrmCase): IntakeRequest {
  const problems: Problem[] = [];
  if (!record.case_number) problems.push({ field: "case_number", message: "Missing" });
  if (!record.member?.id) problems.push({ field: "member.id", message: "Missing" });
  if (!record.provider?.npi) problems.push({ field: "provider.npi", message: "Missing" });
  if (!record.request?.cpt) problems.push({ field: "request.cpt", message: "Missing" });
  if (!record.request?.date) problems.push({ field: "request.date", message: "Missing" });
  for (const [i, a] of (record.attachments ?? []).entries()) {
    if (!a.type || !a.text) problems.push({ field: `attachments[${i}]`, message: "Each attachment needs a type and text" });
  }
  if (problems.length) throw new AdapterError(problems);
  return {
    source: "crm",
    source_id: record.case_number!,
    received_at: record.created,
    priority: record.request!.urgent ? "expedited" : "standard",
    member: { id: record.member!.id!, name: record.member!.name ?? "" },
    provider: { npi: record.provider!.npi!, name: record.provider!.name ?? "" },
    service: { code: record.request!.cpt!, diagnosis_codes: record.request!.icd10 ?? [], date_start: record.request!.date! },
    documents: (record.attachments ?? []).map((a) => ({ doc_type: a.type!, title: a.title ?? a.type!, text: a.text! })),
  };
}
