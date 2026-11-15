// Where messages that didn't get through wait: one JSON file per message.
//
//   out/rejected/  the message itself is wrong; a person fixes the source and replays
//   out/parked/    delivery failed (outage, timeouts, bad config); replay when it's fixed
//
// Each file keeps the original message, so nothing is lost even if the source is gone.

import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Problem } from "./canonical.ts";
import type { Message } from "./pipeline.ts";

export type Kind = "rejected" | "parked";

export type StoredRecord = {
  kind: Kind;
  ref: string;
  source_id: string | null;
  trace_id: string;
  reason: string;
  problems: Problem[];
  attempts: number;
  at: string;
  message: Message;
};

function fileName(ref: string): string {
  return ref.replace(/[^A-Za-z0-9._-]+/g, "_") + ".json";
}

export class Outbox {
  readonly dir: string;

  constructor(dir: string) {
    this.dir = dir;
  }

  save(record: StoredRecord): void {
    this.remove(record.ref); // a message lives in at most one place
    const dir = join(this.dir, record.kind);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, fileName(record.ref)), JSON.stringify(record, null, 1) + "\n", "utf8");
  }

  remove(ref: string): void {
    for (const kind of ["rejected", "parked"] as const) {
      rmSync(join(this.dir, kind, fileName(ref)), { force: true });
    }
  }

  list(kind?: Kind): StoredRecord[] {
    const kinds: Kind[] = kind ? [kind] : ["rejected", "parked"];
    return kinds.flatMap((k) => {
      let files: string[] = [];
      try {
        files = readdirSync(join(this.dir, k)).filter((f) => f.endsWith(".json")).sort();
      } catch {
        return [];
      }
      return files.map((f) => JSON.parse(readFileSync(join(this.dir, k, f), "utf8")) as StoredRecord);
    });
  }
}
