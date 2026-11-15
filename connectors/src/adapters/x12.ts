// X12 278 request (005010X217, from a clearinghouse) -> internal request.
//
// A narrow parser for the parts the workflow needs: who the requester and the member
// are, the diagnoses, the service date and the service code. It reads the separators
// from the ISA header instead of assuming them, and checks the segment count in SE01.
// It is not a full 278 implementation; anything situational in the X12 guide that
// isn't listed here is ignored. Fixtures are hand-built synthetic files.
//
// Urgency: how a clearinghouse flags an expedited 278 is set by its companion guide,
// which this project doesn't have, so X12 requests arrive as standard. It's listed as
// an open question for the integration workshop.

import { AdapterError, isoDate, type IntakeRequest, type Problem } from "../canonical.ts";

export type Segments = { segments: string[][]; component: string };

export function tokenize(text: string): Segments {
  const start = text.indexOf("ISA");
  if (start < 0) throw new AdapterError([{ field: "ISA", message: "No ISA header: not an X12 interchange" }]);
  const isa = text.slice(start);
  if (isa.length < 106) throw new AdapterError([{ field: "ISA", message: "The ISA header is shorter than its fixed 106 characters" }]);
  const element = isa[3];
  const component = isa[104];
  const terminator = isa[105];
  const segments = isa
    .split(terminator)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => s.split(element));
  if (segments[0].length !== 17) {
    throw new AdapterError([{ field: "ISA", message: `The ISA header has ${segments[0].length - 1} elements; it must have 16` }]);
  }
  return { segments, component };
}

export function fromX12_278(text: string): IntakeRequest {
  const { segments, component } = tokenize(text);
  const problems: Problem[] = [];
  const find = (id: string) => segments.find((s) => s[0] === id);

  const gs = find("GS");
  if (!gs || !(gs[8] ?? "").startsWith("005010X217")) {
    problems.push({ field: "GS08", message: "Expected a 005010X217 (278 request and response) functional group" });
  }
  const stIndex = segments.findIndex((s) => s[0] === "ST" && s[1] === "278");
  const seIndex = segments.findIndex((s, i) => i > stIndex && s[0] === "SE");
  if (stIndex < 0 || seIndex < 0) throw new AdapterError([{ field: "ST", message: "No ST*278 ... SE transaction in the file" }]);
  const declared = Number(segments[seIndex][1]);
  const actual = seIndex - stIndex + 1;
  if (declared !== actual) problems.push({ field: "SE01", message: `SE01 says ${declared} segments but the transaction has ${actual}` });

  const bht = find("BHT");
  if (!bht) problems.push({ field: "BHT", message: "Missing BHT segment" });
  else if (bht[2] !== "13") problems.push({ field: "BHT02", message: `BHT02 is ${bht[2]}; a request must be 13` });

  // Walk the hierarchical levels: 20 payer, 21 requester, 22 subscriber, EV event, SS service.
  let level = "";
  let provider: { npi: string; name: string } | null = null;
  let member: { id: string; name: string } | null = null;
  const diagnoses: string[] = [];
  let serviceDate = "";
  let serviceCode = "";
  for (const s of segments.slice(stIndex, seIndex)) {
    if (s[0] === "HL") level = s[3] ?? "";
    else if (s[0] === "NM1" && level === "21" && s[1] === "1P") {
      if (s[8] !== "XX") problems.push({ field: "NM1*1P", message: "The requester has no XX (NPI) identifier" });
      else provider = { npi: s[9] ?? "", name: [s[4], s[3]].filter(Boolean).join(" ") };
    } else if (s[0] === "NM1" && level === "22" && s[1] === "IL") {
      if (s[8] !== "MI") problems.push({ field: "NM1*IL", message: "The subscriber has no MI (member ID) identifier" });
      else member = { id: s[9] ?? "", name: [s[4], s[3]].filter(Boolean).join(" ") };
    } else if (s[0] === "HI") {
      for (const composite of s.slice(1)) {
        const [qualifier, code] = composite.split(component);
        if (qualifier === "ABK" || qualifier === "ABF") diagnoses.push(code);
      }
    } else if (s[0] === "DTP" && s[1] === "472") {
      serviceDate = isoDate((s[3] ?? "").split("-")[0]);
    } else if ((s[0] === "SV1" || s[0] === "SV2") && level === "SS") {
      const composite = s[0] === "SV1" ? s[1] : s[2];
      const [qualifier, code] = (composite ?? "").split(component);
      if (qualifier === "HC") serviceCode = code;
    }
  }
  if (!provider) problems.push({ field: "loop 2010B", message: "No requester (NM1*1P) found" });
  if (!member) problems.push({ field: "loop 2010C", message: "No subscriber (NM1*IL) found" });
  if (!serviceDate) problems.push({ field: "DTP*472", message: "No service date" });
  if (!serviceCode) problems.push({ field: "SV1/SV2", message: "No HC (CPT/HCPCS) service code" });
  if (problems.length) throw new AdapterError(problems);

  const created = bht![4] && bht![5] ? `${isoDate(bht![4])}T${bht![5].slice(0, 2)}:${bht![5].slice(2, 4)}:00Z` : undefined;
  return {
    source: "x12",
    source_id: bht![3],
    received_at: created,
    priority: "standard",
    member: member!,
    provider: provider!,
    service: { code: serviceCode, diagnosis_codes: diagnoses, date_start: serviceDate },
    documents: [],
  };
}
