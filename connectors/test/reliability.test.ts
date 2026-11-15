// Step 8: failure on purpose. A real local HTTP server plays the workflow service and
// misbehaves: it times out, returns 503 and 429, refuses the token, or goes away.

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync, cpSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";
import { fileURLToPath } from "node:url";
import { backoff, deliver } from "../src/delivery.ts";
import { Outbox } from "../src/outbox.ts";
import { processMessage, type Message } from "../src/pipeline.ts";
import { run } from "../src/cli.ts";

type Behaviour = (call: number, body: { source_id: string }, res: ServerResponse) => void;

// A fake workflow service that also remembers which messages created a case.
async function fakeWorkflow(behaviour: Behaviour) {
  const created = new Set<string>();
  let calls = 0;
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      calls += 1;
      behaviour(calls, JSON.parse(raw || "{}"), res);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}`,
    calls: () => calls,
    created,
    accept(body: { source_id: string }, res: ServerResponse) {
      const isNew = !created.has(body.source_id);
      created.add(body.source_id);
      res.writeHead(isNew ? 201 : 200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ outcome: isNew ? "created" : "replayed", case_id: created.size, state: "ready_for_review" }));
    },
    close: () => {
      server.closeAllConnections();
      server.close();
    },
  };
}

const servers: { close: () => void }[] = [];
after(() => servers.forEach((s) => s.close()));

const fixtures = fileURLToPath(new URL("../fixtures", import.meta.url));
const fhirMessage: Message = { source: "fhir", ref: "fhir/fhir-1001.json", raw: readFileSync(join(fixtures, "fhir", "fhir-1001.json"), "utf8") };
const noWait = { sleep: async () => {}, log: () => {} };

test("backoff doubles, adds jitter, caps at 30 s and honours Retry-After", () => {
  const zero = () => 0;
  assert.deepEqual([1, 2, 3, 4].map((a) => backoff(a, 500, zero)), [500, 1000, 2000, 4000]);
  assert.equal(backoff(20, 500, zero), 30_000);
  assert.equal(backoff(1, 500, () => 0.999), 749);
  assert.equal(backoff(1, 500, zero, 5), 5000);
  assert.equal(backoff(1, 500, zero, 120), 30_000);
});

test("AS-13: 503 twice, then success: delivered on the third attempt with growing waits", async () => {
  const server = await fakeWorkflow((call, body, res) => {
    if (call <= 2) {
      res.writeHead(503).end();
      return;
    }
    server.accept(body, res);
  });
  servers.push(server);
  const waits: number[] = [];
  const outcome = await processMessage(fhirMessage, {
    baseUrl: server.url, token: "t", baseDelayMs: 100, random: () => 0, sleep: async (ms) => void waits.push(ms), log: () => {},
  });
  assert.equal(outcome.status, "delivered");
  assert.equal(outcome.attempts, 3);
  assert.deepEqual(waits, [100, 200]);
  assert.equal(server.created.size, 1);
});

test("AS-13: timeouts on every attempt park the record; replay after recovery creates exactly one case", async () => {
  let healthy = false;
  const server = await fakeWorkflow((_call, body, res) => {
    if (healthy) server.accept(body, res);
    else setTimeout(() => res.writeHead(201).end("{}"), 300); // slower than the connector waits
  });
  servers.push(server);
  const outbox = new Outbox(mkdtempSync(join(tmpdir(), "outbox-")));
  const opts = { baseUrl: server.url, token: "t", timeoutMs: 50, maxAttempts: 3, outbox, ...noWait };

  const first = await processMessage(fhirMessage, opts);
  assert.equal(first.status, "parked");
  assert.match(first.status === "parked" ? first.reason : "", /Timed out after 50 ms; gave up after 3 attempts/);
  assert.deepEqual(outbox.list("parked").map((r) => r.ref), ["fhir/fhir-1001.json"]);

  healthy = true;
  const [record] = outbox.list("parked");
  const replay = await processMessage(record.message, opts);
  assert.equal(replay.status, "delivered");
  assert.deepEqual(outbox.list(), []);
  // A late success from the slow attempts and the replay carry the same source_id, so one case.
  assert.equal(server.created.size, 1);
});

test("429 with Retry-After waits as long as the service asks", async () => {
  const server = await fakeWorkflow((call, body, res) => {
    if (call === 1) {
      res.writeHead(429, { "Retry-After": "2" }).end();
      return;
    }
    server.accept(body, res);
  });
  servers.push(server);
  const waits: number[] = [];
  const outcome = await processMessage(fhirMessage, { baseUrl: server.url, token: "t", random: () => 0, sleep: async (ms) => void waits.push(ms), log: () => {} });
  assert.equal(outcome.status, "delivered");
  assert.deepEqual(waits, [2000]);
});

test("a 422 is rejected at once and kept for a person to fix", async () => {
  const server = await fakeWorkflow((_c, _b, res) => {
    res.writeHead(422, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ detail: "Member SYN-M0010 ...", problems: [{ field: "member_id", code: "x", message: "Example problem" }] }));
  });
  servers.push(server);
  const outbox = new Outbox(mkdtempSync(join(tmpdir(), "outbox-")));
  const outcome = await processMessage(fhirMessage, { baseUrl: server.url, token: "t", outbox, ...noWait });
  assert.equal(outcome.status, "rejected");
  assert.equal(server.calls(), 1);
  assert.deepEqual(outbox.list("rejected")[0].problems, [{ field: "member_id", message: "Example problem" }]);
});

test("a refused token parks at once instead of hammering the service", async () => {
  const server = await fakeWorkflow((_c, _b, res) => res.writeHead(401).end());
  servers.push(server);
  const outcome = await processMessage(fhirMessage, { baseUrl: server.url, token: "wrong", ...noWait });
  assert.equal(outcome.status, "parked");
  assert.equal(server.calls(), 1);
});

test("a service that isn't there at all is retried, then parked", async () => {
  const server = await fakeWorkflow(() => {});
  const url = server.url;
  server.close(); // nothing listens on this port any more
  const outcome = await deliver(
    { source: "fhir", source_id: "x", priority: "standard", member: { id: "SYN-M0001", name: "" }, provider: { npi: "1234567893", name: "" },
      service: { code: "72148", diagnosis_codes: ["M54.50"], date_start: "2026-12-01" }, documents: [] },
    { baseUrl: url, token: "t", traceId: "t", maxAttempts: 3, sleep: async () => {} },
  );
  assert.equal(outcome.status, "parked");
  assert.equal(outcome.attempts, 3);
  assert.match(outcome.status === "parked" ? outcome.reason : "", /Can't reach the workflow service/);
});

test("AS-07: a rejected record is replayed from the fixed source and leaves the outbox", async () => {
  const server = await fakeWorkflow((_c, body, res) => server.accept(body, res));
  servers.push(server);
  const work = mkdtempSync(join(tmpdir(), "ingest-"));
  mkdirSync(join(work, "x12"));
  cpSync(join(fixtures, "x12", "278-REQ5003.x12"), join(work, "x12", "278-REQ5003.x12")); // bad NPI check digit
  const env = { CONNECTOR_TOKEN: "t", WORKFLOW_URL: server.url, OUTBOX_DIR: join(work, "out") };
  Object.assign(process.env, env);
  const log = console.log;
  console.log = () => {};
  const errorLog = console.error;
  console.error = () => {};
  try {
    assert.equal(await run(["ingest", work]), 0);
    const outbox = new Outbox(env.OUTBOX_DIR);
    assert.deepEqual(outbox.list("rejected").map((r) => r.problems[0].message), ["Provider NPI check digit is invalid"]);
    assert.equal(server.calls(), 0); // never sent

    const path = join(work, "x12", "278-REQ5003.x12");
    writeFileSync(path, readFileSync(path, "utf8").replace("XX*1234567890", "XX*1234567893"));
    assert.equal(await run(["replay", work]), 0);
    assert.deepEqual(outbox.list(), []);
    assert.deepEqual([...server.created], ["REQ5003"]);
  } finally {
    console.log = log;
    console.error = errorLog;
  }
});
