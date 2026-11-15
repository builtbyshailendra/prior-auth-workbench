// One source message in, one outcome out: parse -> check -> send -> remember failures.
// Logs one JSON line per message with IDs only: no names, no note text.

import { randomUUID } from "node:crypto";
import { AdapterError, type IntakeRequest, type Problem, type Source, validate } from "./canonical.ts";
import { fromCrm } from "./adapters/crm.ts";
import { fromFax } from "./adapters/fax.ts";
import { fromFhirBundle } from "./adapters/fhir.ts";
import { fromX12_278 } from "./adapters/x12.ts";
import { deliver, type DeliveryOptions, type DeliveryResult } from "./delivery.ts";
import type { Outbox } from "./outbox.ts";

export type Message = { source: Source; ref: string; raw: string };

export type Outcome = DeliveryResult & { source: Source; ref: string; sourceId: string | null; traceId: string };

export function parse(message: Message): IntakeRequest {
  switch (message.source) {
    case "fhir":
      return fromFhirBundle(JSON.parse(message.raw));
    case "x12":
      return fromX12_278(message.raw);
    case "fax":
      return fromFax(JSON.parse(message.raw));
    case "crm":
      return fromCrm(JSON.parse(message.raw));
    default:
      throw new AdapterError([{ field: "source", message: `No adapter for ${String(message.source)}` }]);
  }
}

export type PipelineOptions = Omit<DeliveryOptions, "traceId"> & { log?: (line: string) => void; outbox?: Outbox };

export async function processMessage(message: Message, options: PipelineOptions): Promise<Outcome> {
  const traceId = randomUUID().replaceAll("-", "");
  const log = options.log ?? ((line) => console.log(line));
  let request: IntakeRequest | null = null;
  let result: DeliveryResult;
  try {
    request = parse(message);
    const problems = validate(request);
    result = problems.length
      ? { status: "rejected", reason: "Failed the connector's checks", problems, attempts: 0 }
      : await deliver(request, { ...options, traceId });
  } catch (error) {
    const problems: Problem[] = error instanceof AdapterError ? error.problems : [{ field: "message", message: (error as Error).message }];
    result = { status: "rejected", reason: "Couldn't read the source message", problems, attempts: 0 };
  }

  const sourceId = request?.source_id ?? null;
  if (options.outbox) {
    if (result.status === "delivered") options.outbox.remove(message.ref);
    else {
      options.outbox.save({
        kind: result.status,
        ref: message.ref,
        source_id: sourceId,
        trace_id: traceId,
        reason: result.reason,
        problems: result.status === "rejected" ? result.problems : [],
        attempts: result.attempts,
        at: new Date().toISOString(),
        message,
      });
    }
  }
  log(
    JSON.stringify({
      event: "message",
      source: message.source,
      ref: message.ref,
      source_id: sourceId,
      trace_id: traceId,
      status: result.status,
      attempts: result.attempts,
      ...(result.status === "delivered"
        ? { outcome: result.outcome, case_id: result.caseId, state: result.state }
        : { reason: result.reason, ...(result.status === "rejected" ? { problems: result.problems } : {}) }),
    }),
  );
  return { ...result, source: message.source, ref: message.ref, sourceId, traceId };
}
