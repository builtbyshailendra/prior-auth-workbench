// The internal request format every adapter produces, and the checks it must pass
// before it's sent. It mirrors workflow/app/schemas.py; the workflow service checks
// everything again, so these checks only stop obviously bad records earlier.

export type Source = "fhir" | "x12" | "fax" | "crm";
export type Priority = "standard" | "expedited";

export type DocumentIn = { doc_type: string; title: string; text: string };

export type IntakeRequest = {
  source: Source;
  source_id: string;
  received_at?: string;
  priority: Priority;
  member: { id: string; name: string };
  provider: { npi: string; name: string };
  service: { code: string; diagnosis_codes: string[]; date_start: string; date_end?: string };
  documents: DocumentIn[];
};

export type Problem = { field: string; message: string };

/** Thrown by an adapter when a source message can't be turned into a request at all. */
export class AdapterError extends Error {
  readonly problems: Problem[];
  constructor(problems: Problem[]) {
    super(problems.map((p) => `${p.field}: ${p.message}`).join("; "));
    this.problems = problems;
  }
}

const SERVICE_CODE = /^(\d{5}|\d{4}[FT]|[A-V]\d{4})$/;
const DIAGNOSIS_CODE = /^[A-TV-Z]\d[0-9A-Z](\.?[0-9A-Z]{1,4})?$/;
const SYNTHETIC_MEMBER = /^SYN-M\d{4,}$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Luhn over the nine digits with the 80840 prefix, which works out to adding 24. */
export function npiCheckDigit(firstNine: string): number {
  let total = 24;
  [...firstNine].reverse().forEach((char, position) => {
    let digit = Number(char);
    if (position % 2 === 0) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  });
  return (10 - (total % 10)) % 10;
}

export function npiIsValid(npi: string): boolean {
  return /^\d{10}$/.test(npi) && npiCheckDigit(npi.slice(0, 9)) === Number(npi[9]);
}

export function validate(request: IntakeRequest): Problem[] {
  const problems: Problem[] = [];
  if (!request.source_id) problems.push({ field: "source_id", message: "Every message needs an ID from its source system" });
  if (!SYNTHETIC_MEMBER.test(request.member.id)) problems.push({ field: "member.id", message: "Member ID must be a synthetic ID like SYN-M0001" });
  if (!/^\d{10}$/.test(request.provider.npi)) problems.push({ field: "provider.npi", message: "Provider NPI must be exactly 10 digits" });
  else if (!npiIsValid(request.provider.npi)) problems.push({ field: "provider.npi", message: "Provider NPI check digit is invalid" });
  if (!SERVICE_CODE.test(request.service.code)) problems.push({ field: "service.code", message: `Service code "${request.service.code}" isn't a CPT or HCPCS code` });
  if (request.service.diagnosis_codes.length === 0) problems.push({ field: "service.diagnosis_codes", message: "At least one diagnosis code is needed" });
  for (const code of request.service.diagnosis_codes) {
    if (!DIAGNOSIS_CODE.test(code)) problems.push({ field: "service.diagnosis_codes", message: `Diagnosis code "${code}" isn't an ICD-10-CM code` });
  }
  if (!ISO_DATE.test(request.service.date_start)) problems.push({ field: "service.date_start", message: "Service date must be YYYY-MM-DD" });
  return problems;
}

/** Turns YYYYMMDD (as X12 and many feeds send dates) into YYYY-MM-DD. */
export function isoDate(compact: string): string {
  if (!/^\d{8}$/.test(compact)) return compact;
  return `${compact.slice(0, 4)}-${compact.slice(4, 6)}-${compact.slice(6, 8)}`;
}
