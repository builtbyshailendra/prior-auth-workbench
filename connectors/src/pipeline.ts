// One source message in, one outcome out: parse -> check -> send.
// Logs one JSON line per message with IDs only: no names, no note text.

import { randomUUID } from "node:crypto";
import { AdapterError, type IntakeRequest, type Source, validate } from "./canonical.ts";
import { fromFhirBundle } from "./adapters/fhir.ts";
import { deliver, type DeliveryOptions, type DeliveryResult } from "./delivery.ts";

export type Message = { source: Source; ref: string; raw: string };

export type Outcome = DeliveryResult & { source: Source; ref: string; sourceId: string | null; traceId: string };

export function parse(message: Message): IntakeRequest {
  switch (message.source) {
    case "fhir":
      return fromFhirBundle(JSON.parse(message.raw));
    default:
      throw new AdapterError([{ field: "source", message: `No adapter for ${message.source} yet` }]);
  }
}

export type PipelineOptions = Omit<DeliveryOptions, "traceId"> & { log?: (line: string) => void };

export async function processMessage(message: Message, options: PipelineOptions): Promise<Outcome> {
  const traceId = randomUUID().replaceAll("-", "");
  const log = options.log ?? ((line) => console.log(line));
  let request: IntakeRequest;
  let result: DeliveryResult;
  try {
    request = parse(message);
  } catch (error) {
    const problems = error instanceof AdapterError ? error.problems : [{ field: "message", message: (error as Error).message }];
    result = { status: "rejected", reason: "Couldn't read the source message", problems, attempts: 0 };
    const outcome: Outcome = { ...result, source: message.source, ref: message.ref, sourceId: null, traceId };
    log(JSON.stringify({ event: "message", source: message.source, ref: message.ref, trace_id: traceId, status: "rejected", problems }));
    return outcome;
  }
  const problems = validate(request);
  if (problems.length) {
    result = { status: "rejected", reason: "Failed the connector's checks", problems, attempts: 0 };
  } else {
    result = await deliver(request, { ...options, traceId });
  }
  log(
    JSON.stringify({
      event: "message",
      source: message.source,
      ref: message.ref,
      source_id: request.source_id,
      trace_id: traceId,
      status: result.status,
      ...(result.status === "delivered" ? { outcome: result.outcome, case_id: result.caseId, state: result.state } : { reason: result.reason }),
    }),
  );
  return { ...result, source: message.source, ref: message.ref, sourceId: request.source_id, traceId };
}
