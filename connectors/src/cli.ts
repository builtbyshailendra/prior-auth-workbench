// Command line: send every message in a folder to the workflow service.
//
//   CONNECTOR_TOKEN=... node src/cli.ts ingest fixtures
//
// WORKFLOW_URL defaults to http://127.0.0.1:8000.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Source } from "./canonical.ts";
import { processMessage, type Message } from "./pipeline.ts";

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
  return messages;
}

async function main(argv: string[]) {
  const [command, dir = "fixtures"] = argv;
  const token = process.env.CONNECTOR_TOKEN ?? "";
  const baseUrl = process.env.WORKFLOW_URL ?? "http://127.0.0.1:8000";
  if (command !== "ingest") {
    console.error("usage: node src/cli.ts ingest <folder>");
    process.exit(2);
  }
  if (!token) {
    console.error("Set CONNECTOR_TOKEN to the token the workflow service expects.");
    process.exit(2);
  }
  const counts: Record<string, number> = {};
  for (const message of readMessages(dir)) {
    const outcome = await processMessage(message, { baseUrl, token });
    counts[outcome.status] = (counts[outcome.status] ?? 0) + 1;
  }
  console.error(`Done: ${JSON.stringify(counts)}`);
  process.exit(counts.failed ? 1 : 0);
}

if (import.meta.main) await main(process.argv.slice(2));
