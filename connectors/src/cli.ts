// Command line.
//
//   node src/cli.ts ingest <folder>    send every message in the folder
//   node src/cli.ts replay [folder]    retry everything parked or rejected; with a folder,
//                                      re-read each message from it first (so a fixed source wins)
//   node src/cli.ts status             list what's waiting in the outbox
//
// Environment: CONNECTOR_TOKEN (required), WORKFLOW_URL (default http://127.0.0.1:8000),
// OUTBOX_DIR (default ./out), MAX_ATTEMPTS, TIMEOUT_MS, BASE_DELAY_MS.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { documentList, parseCsv } from "./adapters/fax.ts";
import type { Source } from "./canonical.ts";
import { Outbox } from "./outbox.ts";
import { processMessage, type Message, type PipelineOptions } from "./pipeline.ts";

export function readMessages(root: string): Message[] {
  const messages: Message[] = [];
  const files = (dir: string, ext: string) => {
    try {
      return readdirSync(join(root, dir)).filter((f) => f.endsWith(ext)).sort();
    } catch {
      return [];
    }
  };
  for (const file of files("fhir", ".json")) {
    messages.push({ source: "fhir" as Source, ref: `fhir/${file}`, raw: readFileSync(join(root, "fhir", file), "utf8") });
  }
  for (const file of files("x12", ".x12")) {
    messages.push({ source: "x12", ref: `x12/${file}`, raw: readFileSync(join(root, "x12", file), "utf8") });
  }
  for (const file of files("crm", ".json")) {
    messages.push({ source: "crm", ref: `crm/${file}`, raw: readFileSync(join(root, "crm", file), "utf8") });
  }
  // The fax index lists documents by path; load their text now so the adapter only maps.
  if (files("fax", ".csv").includes("index.csv")) {
    const rows = parseCsv(readFileSync(join(root, "fax", "index.csv"), "utf8"));
    rows.forEach((row) => {
      const documents = documentList(row.documents ?? "").map((d) => {
        let text: string | null = null;
        try {
          text = readFileSync(join(root, "fax", d.file), "utf8");
        } catch {
          text = null;
        }
        return { ...d, text };
      });
      // Referenced by fax ID, not row number, so a fixed row still matches on replay.
      messages.push({ source: "fax", ref: `fax/${row.fax_id || "row"}`, raw: JSON.stringify({ row, documents }) });
    });
  }
  return messages;
}

function options(outbox: Outbox): PipelineOptions {
  const number = (name: string) => (process.env[name] ? Number(process.env[name]) : undefined);
  return {
    baseUrl: process.env.WORKFLOW_URL ?? "http://127.0.0.1:8000",
    token: process.env.CONNECTOR_TOKEN ?? "",
    outbox,
    maxAttempts: number("MAX_ATTEMPTS"),
    timeoutMs: number("TIMEOUT_MS"),
    baseDelayMs: number("BASE_DELAY_MS"),
  };
}

export async function run(argv: string[]): Promise<number> {
  const [command, dir] = argv;
  const outbox = new Outbox(process.env.OUTBOX_DIR ?? "out");
  const counts: Record<string, number> = {};
  const tally = (status: string) => (counts[status] = (counts[status] ?? 0) + 1);

  if (command === "status") {
    for (const r of outbox.list()) console.log(`${r.kind}\t${r.ref}\t${r.reason}`);
    return 0;
  }
  if (command !== "ingest" && command !== "replay") {
    console.error("usage: node src/cli.ts ingest <folder> | replay [folder] | status");
    return 2;
  }
  if (!process.env.CONNECTOR_TOKEN) {
    console.error("Set CONNECTOR_TOKEN to the token the workflow service expects.");
    return 2;
  }

  if (command === "ingest") {
    for (const message of readMessages(dir ?? "fixtures")) tally((await processMessage(message, options(outbox))).status);
  } else {
    const fresh = new Map((dir ? readMessages(dir) : []).map((m) => [m.ref, m]));
    for (const record of outbox.list()) {
      tally((await processMessage(fresh.get(record.ref) ?? record.message, options(outbox))).status);
    }
  }
  console.error(`Done: ${JSON.stringify(counts)}`);
  // Parked messages need someone to look; rejected ones are reported but expected now and then.
  return counts.parked ? 1 : 0;
}

if (import.meta.main) process.exit(await run(process.argv.slice(2)));
