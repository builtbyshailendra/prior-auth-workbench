import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { AdapterError, validate } from "../src/canonical.ts";
import { fromCrm } from "../src/adapters/crm.ts";
import { documentList, fromFax, parseCsv } from "../src/adapters/fax.ts";
import { fromX12_278, tokenize } from "../src/adapters/x12.ts";
import { readMessages } from "../src/cli.ts";

const fixture = (path: string) => readFileSync(new URL(`../fixtures/${path}`, import.meta.url), "utf8");
const problemsOf = (fn: () => unknown) => {
  try {
    fn();
  } catch (error) {
    if (error instanceof AdapterError) return error.problems.map((p) => p.field);
    throw error;
  }
  return [];
};

// --- X12 278 ---------------------------------------------------------------------------

test("a 278 request maps to the internal request", () => {
  const request = fromX12_278(fixture("x12/278-REQ5001.x12"));
  assert.equal(request.source, "x12");
  assert.equal(request.source_id, "REQ5001");
  assert.equal(request.received_at, "2026-11-16T09:05:00Z");
  assert.deepEqual(request.member, { id: "SYN-M0010", name: "ROWAN FERREIRA" });
  assert.deepEqual(request.provider, { npi: "1234567893", name: "SYNTHETIC SPINE CLINIC" });
  assert.deepEqual(request.service, { code: "72148", diagnosis_codes: ["M5416"], date_start: "2026-12-07" });
  assert.equal(request.priority, "standard"); // urgency depends on the clearinghouse's companion guide
  assert.deepEqual(request.documents, []);
  assert.deepEqual(validate(request), []);
});

test("separators come from the ISA header, not assumptions", () => {
  // The same transaction with | between elements, > between components and a newline ending each segment.
  const swapped = fixture("x12/278-REQ5001.x12").replaceAll("*", "|").replaceAll(":", ">").replaceAll("~\n", "\n");
  assert.equal(swapped.indexOf("\n"), 105); // the ISA is still 106 characters, ending in the new terminator
  const request = fromX12_278(swapped);
  assert.equal(request.service.code, "72148");
  assert.deepEqual(request.service.diagnosis_codes, ["M5416"]);
});

test("the segment count in SE01 is checked", () => {
  const broken = fixture("x12/278-REQ5001.x12").replace(/SE\*\d+\*0001/, "SE*99*0001");
  assert.throws(() => fromX12_278(broken), /SE01 says 99 segments but the transaction has 15/);
});

test("a response (BHT02 11) or a requester without an NPI is refused", () => {
  const response = fixture("x12/278-REQ5001.x12").replace("BHT*0007*13*", "BHT*0007*11*");
  assert.deepEqual(problemsOf(() => fromX12_278(response)), ["BHT02"]);
  const noNpi = fixture("x12/278-REQ5001.x12").replace("*****XX*1234567893", "*****PI*12345");
  assert.deepEqual(problemsOf(() => fromX12_278(noNpi)), ["NM1*1P", "loop 2010B"]);
});

test("garbage and short headers fail clearly", () => {
  assert.throws(() => tokenize("hello"), /No ISA header/);
  assert.throws(() => tokenize("ISA*00*short~"), /shorter than its fixed 106 characters/);
});

test("the bad-NPI fixture parses but fails the connector's checks", () => {
  const request = fromX12_278(fixture("x12/278-REQ5003.x12"));
  assert.deepEqual(validate(request), [{ field: "provider.npi", message: "Provider NPI check digit is invalid" }]);
});

// --- fax index -------------------------------------------------------------------------

test("the CSV reader handles quoted commas and doubled quotes", () => {
  const rows = parseCsv('a,b,c\r\n1,"x, y","say ""hi"""\r\n\r\n2,,last\n');
  assert.deepEqual(rows, [
    { a: "1", b: "x, y", c: 'say "hi"' },
    { a: "2", b: "", c: "last" },
  ]);
  assert.deepEqual(documentList("clinician_note=notes/a.txt; sleep_questionnaire=notes/b.txt"), [
    { doc_type: "clinician_note", file: "notes/a.txt" },
    { doc_type: "sleep_questionnaire", file: "notes/b.txt" },
  ]);
});

test("a fax index row and its documents map to the internal request", () => {
  const fax = readMessages(fileURLToPath(new URL("../fixtures", import.meta.url))).filter((m) => m.source === "fax");
  assert.equal(fax.length, 3);
  const request = fromFax(JSON.parse(fax[0].raw));
  assert.equal(request.source_id, "FAX-2001");
  assert.equal(request.provider.name, "Synthetic Orthopedics, PLLC");
  assert.deepEqual(request.documents.map((d) => d.doc_type), ["clinician_note", "conservative_treatment_record"]);
  assert.match(request.documents[0].text, /Six weeks of physical therapy/);
  assert.equal(fromFax(JSON.parse(fax[1].raw)).priority, "expedited");
});

test("a fax row pointing at a missing document is refused", () => {
  const message = {
    row: { fax_id: "FAX-9", member_id: "SYN-M0001", provider_npi: "1234567893", service_code: "72148", diagnosis_codes: "M54.50", service_date: "2026-12-01" },
    documents: [{ doc_type: "clinician_note", file: "notes/gone.txt", text: null }],
  };
  assert.throws(() => fromFax(message), /Faxed document notes\/gone.txt is listed but missing/);
  assert.deepEqual(problemsOf(() => fromFax({ row: {}, documents: [] })).length, 6);
});

// --- CRM -------------------------------------------------------------------------------

test("a CRM case maps to the internal request", () => {
  const request = fromCrm(JSON.parse(fixture("crm/CRM-3001.json")));
  assert.equal(request.source_id, "CRM-3001");
  assert.equal(request.service.code, "97110");
  assert.deepEqual(request.documents.map((d) => d.doc_type), ["plan_of_care", "progress_note"]);
  assert.deepEqual(validate(request), []);
});

test("an urgent CRM case is expedited, and missing fields are all listed", () => {
  const record = JSON.parse(fixture("crm/CRM-3001.json"));
  record.request.urgent = true;
  assert.equal(fromCrm(record).priority, "expedited");
  assert.deepEqual(problemsOf(() => fromCrm({ attachments: [{ type: "x" }] })), [
    "case_number", "member.id", "provider.npi", "request.cpt", "request.date", "attachments[0]",
  ]);
});
