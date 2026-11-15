import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { processMessage, type Message } from "../src/pipeline.ts";

const raw = readFileSync(new URL("../fixtures/fhir/fhir-1001.json", import.meta.url), "utf8");
const message: Message = { source: "fhir", ref: "fhir/fhir-1001.json", raw };

function fakeFetch(status: number, body: object, calls: Request[] = []): typeof fetch {
  return (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push(new Request(url, init));
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
}

const quiet = { log: () => {} };

test("a delivered message reports the case, and sends the token and a trace ID", async () => {
  const calls: Request[] = [];
  const outcome = await processMessage(message, {
    baseUrl: "http://workflow",
    token: "t0k3n",
    fetchImpl: fakeFetch(201, { outcome: "created", case_id: 7, state: "ready_for_review" }, calls),
    ...quiet,
  });
  assert.equal(outcome.status, "delivered");
  assert.equal(outcome.status === "delivered" && outcome.caseId, 7);
  assert.equal(calls[0].url, "http://workflow/api/intake");
  assert.equal(calls[0].headers.get("authorization"), "Bearer t0k3n");
  assert.match(calls[0].headers.get("x-trace-id") ?? "", /^[0-9a-f]{32}$/);
  assert.equal((await calls[0].json()).source_id, "EHR-fhir-1001");
});

test("a 422 from the workflow service is a rejection with its problems", async () => {
  const outcome = await processMessage(message, {
    baseUrl: "http://workflow",
    token: "t",
    fetchImpl: fakeFetch(422, { detail: "bad", problems: [{ field: "provider_npi", code: "x", message: "Provider NPI check digit is invalid" }] }),
    ...quiet,
  });
  assert.equal(outcome.status, "rejected");
  assert.deepEqual(outcome.status === "rejected" && outcome.problems, [{ field: "provider_npi", message: "Provider NPI check digit is invalid" }]);
});

test("an unreadable message is rejected without calling the service", async () => {
  const calls: Request[] = [];
  const outcome = await processMessage({ ...message, raw: "{not json" }, { baseUrl: "x", token: "t", fetchImpl: fakeFetch(201, {}, calls), ...quiet });
  assert.equal(outcome.status, "rejected");
  assert.equal(calls.length, 0);
});

test("log lines carry IDs, never names or note text", async () => {
  const lines: string[] = [];
  await processMessage(message, {
    baseUrl: "http://workflow",
    token: "t",
    fetchImpl: fakeFetch(201, { outcome: "created", case_id: 1, state: "ready_for_review" }),
    log: (line) => lines.push(line),
  });
  assert.equal(lines.length, 1);
  assert.doesNotMatch(lines[0], /Rowan|Ferreira|physical therapy/i);
  assert.match(lines[0], /"source_id":"EHR-fhir-1001"/);
});
