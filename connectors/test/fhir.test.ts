import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { AdapterError, npiCheckDigit, npiIsValid, validate } from "../src/canonical.ts";
import { fromFhirBundle } from "../src/adapters/fhir.ts";

const bundle = (name: string) => JSON.parse(readFileSync(new URL(`../fixtures/fhir/${name}.json`, import.meta.url), "utf8"));

test("NPI check digit matches the CMS worked example, same as the Python side", () => {
  assert.equal(npiCheckDigit("123456789"), 3);
  assert.ok(npiIsValid("1234567893"));
  assert.ok(!npiIsValid("1234567890"));
});

test("a complete FHIR bundle maps to the internal request", () => {
  const request = fromFhirBundle(bundle("fhir-1001"));
  assert.equal(request.source, "fhir");
  assert.equal(request.source_id, "EHR-fhir-1001");
  assert.equal(request.priority, "standard");
  assert.deepEqual(request.member, { id: "SYN-M0010", name: "Rowan Ferreira" });
  assert.deepEqual(request.provider, { npi: "1234567893", name: "Synthetic Spine Clinic" });
  assert.deepEqual(request.service, { code: "72148", diagnosis_codes: ["M54.16"], date_start: "2026-12-07" });
  assert.equal(request.received_at, "2026-11-10T14:05:00Z");
  assert.deepEqual(
    request.documents.map((d) => d.doc_type),
    ["clinician_note", "conservative_treatment_record"],
  );
  assert.match(request.documents[0].text, /Completed 8 weeks of supervised physical therapy/);
  assert.deepEqual(validate(request), []);
});

test("an urgent FHIR order becomes an expedited request", () => {
  assert.equal(fromFhirBundle(bundle("fhir-1002")).priority, "expedited");
});

test("a bundle without a requester NPI or service code is refused with every problem listed", () => {
  const b = bundle("fhir-1001");
  const order = b.entry.find((e: { resource: { resourceType: string } }) => e.resource.resourceType === "ServiceRequest").resource;
  order.code = { coding: [{ system: "http://example.org/other", code: "X" }] };
  b.entry = b.entry.filter((e: { resource: { resourceType: string } }) => e.resource.resourceType !== "Practitioner");
  assert.throws(
    () => fromFhirBundle(b),
    (error: unknown) =>
      error instanceof AdapterError &&
      error.problems.map((p) => p.field).join(",") === "ServiceRequest.requester,ServiceRequest.code",
  );
});

test("a bundle must hold exactly one ServiceRequest", () => {
  const b = bundle("fhir-1001");
  b.entry = b.entry.filter((e: { resource: { resourceType: string } }) => e.resource.resourceType !== "ServiceRequest");
  assert.throws(() => fromFhirBundle(b), /Expected exactly one ServiceRequest, found 0/);
  assert.throws(() => fromFhirBundle({ resourceType: "Patient" } as never), /Expected a FHIR Bundle/);
});

test("documents that aren't plain text, or were entered in error, are skipped", () => {
  const b = bundle("fhir-1001");
  const docs = b.entry.filter((e: { resource: { resourceType: string } }) => e.resource.resourceType === "DocumentReference");
  docs[0].resource.content[0].attachment.contentType = "application/pdf";
  docs[1].resource.status = "entered-in-error";
  assert.deepEqual(fromFhirBundle(b).documents, []);
});

test("the connector's own checks catch a bad NPI before sending", () => {
  const request = fromFhirBundle(bundle("fhir-1001"));
  request.provider.npi = "1234567890";
  assert.deepEqual(validate(request), [{ field: "provider.npi", message: "Provider NPI check digit is invalid" }]);
});
