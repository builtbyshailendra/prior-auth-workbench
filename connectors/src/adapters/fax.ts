// Fax server index (CSV) + the text of each faxed document -> internal request.
//
// A common legacy pattern: the fax server drops documents in a folder and writes an
// index row per fax. Here the documents are already plain text (OCR is out of scope).
// The reader loads the files; this adapter only maps, so it stays easy to test.

import { AdapterError, type IntakeRequest, type Problem } from "../canonical.ts";

export type FaxMessage = {
  row: Record<string, string>;
  documents: { doc_type: string; file: string; text: string | null }[];
};

/** A small CSV reader: quoted fields, doubled quotes inside them, CRLF or LF line ends. */
export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field);
      if (row.some((f) => f !== "")) rows.push(row);
      row = [];
      field = "";
    } else field += c;
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  const [header, ...data] = rows;
  return data.map((r) => Object.fromEntries(header.map((h, i) => [h.trim(), (r[i] ?? "").trim()])));
}

/** "clinician_note=notes/a.txt;sleep_questionnaire=notes/b.txt" -> pairs. */
export function documentList(value: string): { doc_type: string; file: string }[] {
  return value
    .split(";")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const [doc_type, file] = p.split("=");
      return { doc_type: doc_type.trim(), file: (file ?? "").trim() };
    });
}

const REQUIRED = ["fax_id", "member_id", "provider_npi", "service_code", "diagnosis_codes", "service_date"];

export function fromFax(message: FaxMessage): IntakeRequest {
  const { row } = message;
  const problems: Problem[] = REQUIRED.filter((c) => !row[c]).map((c) => ({ field: c, message: "Empty in the fax index" }));
  for (const doc of message.documents) {
    if (doc.text === null) problems.push({ field: "documents", message: `Faxed document ${doc.file} is listed but missing` });
  }
  if (problems.length) throw new AdapterError(problems);
  return {
    source: "fax",
    source_id: row.fax_id,
    received_at: row.received_at || undefined,
    priority: row.priority === "expedited" ? "expedited" : "standard",
    member: { id: row.member_id, name: row.member_name ?? "" },
    provider: { npi: row.provider_npi, name: row.provider_name ?? "" },
    service: {
      code: row.service_code,
      diagnosis_codes: row.diagnosis_codes.split(";").map((d) => d.trim()).filter(Boolean),
      date_start: row.service_date,
    },
    documents: message.documents.map((d) => ({
      doc_type: d.doc_type,
      title: `Faxed ${d.doc_type.replaceAll("_", " ")}`,
      text: d.text as string,
    })),
  };
}
