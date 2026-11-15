// FHIR R4 bundle (from an EHR) -> internal request.
//
// Reads Patient, Coverage, Practitioner, ServiceRequest and DocumentReference resources.
// This is a mapping of the fields the workflow needs, not a FHIR validator, and it claims
// no conformance with the Da Vinci guides.

import { AdapterError, type DocumentIn, type IntakeRequest, type Problem } from "../canonical.ts";

export const SYSTEMS = {
  memberId: "https://tallowmere.example/fhir/member-id", // the fictional plan's own identifier system
  npi: "http://hl7.org/fhir/sid/us-npi",
  cpt: "http://www.ama-assn.org/go/cpt",
  hcpcs: "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
  icd10cm: "http://hl7.org/fhir/sid/icd-10-cm",
  loinc: "http://loinc.org",
  documentType: "https://tallowmere.example/fhir/document-type",
};

// LOINC 11506-3 is "Progress note". Everything else uses the plan's own document-type codes.
const LOINC_DOCUMENT_TYPES: Record<string, string> = { "11506-3": "clinician_note" };

type Coding = { system?: string; code?: string };
type CodeableConcept = { coding?: Coding[] };
type Identifier = { system?: string; value?: string };
type Reference = { reference?: string };
type HumanName = { family?: string; given?: string[]; text?: string };
type Resource = {
  resourceType: string;
  id?: string;
  identifier?: Identifier[];
  name?: HumanName[] | string;
  [key: string]: unknown;
};
type Bundle = { resourceType: "Bundle"; id?: string; identifier?: Identifier; entry?: { fullUrl?: string; resource?: Resource }[] };

function nameOf(resource: Resource | undefined): string {
  const names = resource?.name;
  if (!Array.isArray(names) || names.length === 0) return typeof names === "string" ? names : "";
  const n = names[0];
  return n.text ?? [...(n.given ?? []), n.family ?? ""].join(" ").trim();
}

function identifier(resource: Resource | undefined, system: string): string | undefined {
  return resource?.identifier?.find((i) => i.system === system)?.value;
}

function codesFrom(concepts: CodeableConcept[] | undefined, systems: string[]): string[] {
  return (concepts ?? []).flatMap((c) => c.coding ?? []).filter((c) => c.system && systems.includes(c.system) && c.code).map((c) => c.code!);
}

export function fromFhirBundle(bundle: Bundle): IntakeRequest {
  const problems: Problem[] = [];
  if (bundle?.resourceType !== "Bundle") throw new AdapterError([{ field: "resourceType", message: "Expected a FHIR Bundle" }]);

  // Index resources by "Type/id" and by fullUrl, so references resolve either way.
  const byRef = new Map<string, Resource>();
  const resources: Resource[] = [];
  for (const entry of bundle.entry ?? []) {
    const r = entry.resource;
    if (!r) continue;
    resources.push(r);
    if (r.id) byRef.set(`${r.resourceType}/${r.id}`, r);
    if (entry.fullUrl) byRef.set(entry.fullUrl, r);
  }
  const resolve = (ref: Reference | undefined) => (ref?.reference ? byRef.get(ref.reference) : undefined);

  const serviceRequests = resources.filter((r) => r.resourceType === "ServiceRequest");
  if (serviceRequests.length !== 1) {
    throw new AdapterError([{ field: "ServiceRequest", message: `Expected exactly one ServiceRequest, found ${serviceRequests.length}` }]);
  }
  const order = serviceRequests[0];

  const patient = resolve(order.subject as Reference);
  if (!patient) problems.push({ field: "ServiceRequest.subject", message: "Doesn't point to a Patient in the bundle" });
  const memberId = identifier(patient, SYSTEMS.memberId);
  if (patient && !memberId) problems.push({ field: "Patient.identifier", message: `No member ID with system ${SYSTEMS.memberId}` });

  const practitioner = resolve(order.requester as Reference);
  const npi = identifier(practitioner, SYSTEMS.npi);
  if (!npi) problems.push({ field: "ServiceRequest.requester", message: "Requester has no NPI identifier" });

  const serviceCodes = codesFrom([order.code as CodeableConcept], [SYSTEMS.cpt, SYSTEMS.hcpcs]);
  if (serviceCodes.length === 0) problems.push({ field: "ServiceRequest.code", message: "No CPT or HCPCS code" });
  const diagnoses = codesFrom(order.reasonCode as CodeableConcept[], [SYSTEMS.icd10cm]);

  const occurrence = (order.occurrenceDateTime as string | undefined) ?? (order.occurrencePeriod as { start?: string } | undefined)?.start;
  if (!occurrence) problems.push({ field: "ServiceRequest.occurrence", message: "No service date" });

  if (problems.length) throw new AdapterError(problems);

  const priority = ["urgent", "asap", "stat"].includes(String(order.priority)) ? "expedited" : "standard";
  const documents: DocumentIn[] = resources
    .filter((r) => r.resourceType === "DocumentReference" && r.status !== "entered-in-error")
    .map((doc) => documentFrom(doc))
    .filter((d): d is DocumentIn => d !== null);

  const sourceId = order.identifier?.[0]?.value ?? bundle.identifier?.value ?? order.id ?? "";
  return {
    source: "fhir",
    source_id: sourceId,
    received_at: (order.authoredOn as string | undefined) ?? undefined,
    priority,
    member: { id: memberId!, name: nameOf(patient) },
    provider: { npi: npi!, name: nameOf(practitioner) },
    service: { code: serviceCodes[0], diagnosis_codes: diagnoses, date_start: occurrence!.slice(0, 10) },
    documents,
  };
}

function documentFrom(doc: Resource): DocumentIn | null {
  const codings = ((doc.type as CodeableConcept | undefined)?.coding ?? []) as Coding[];
  const ownType = codings.find((c) => c.system === SYSTEMS.documentType)?.code;
  const loincType = codings.map((c) => (c.system === SYSTEMS.loinc && c.code ? LOINC_DOCUMENT_TYPES[c.code] : undefined)).find(Boolean);
  const attachment = (doc.content as { attachment?: { contentType?: string; data?: string; title?: string } }[] | undefined)?.[0]?.attachment;
  if (!attachment?.data || !(attachment.contentType ?? "").startsWith("text/plain")) return null;
  return {
    doc_type: ownType ?? loincType ?? "other",
    title: attachment.title ?? (doc.description as string | undefined) ?? "Document",
    text: Buffer.from(attachment.data, "base64").toString("utf8"),
  };
}
