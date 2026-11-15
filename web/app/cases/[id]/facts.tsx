"use client";

import { useState } from "react";
import { api, ApiError, type CaseDetail, type Fact, type Me } from "@/lib/api";

function valueText(fact: Fact | undefined): string {
  if (!fact) return "Needs entry";
  if (fact.status === "not_documented") return "Not documented";
  if (fact.status === "dropped") return "Couldn't verify";
  if (fact.value === true) return "Yes";
  if (fact.value === false) return "No";
  if (fact.value === null) return "Not documented";
  return String(fact.value);
}

function source(fact: Fact): string {
  if (fact.method === "manual") return `Entered by ${fact.entered_by ?? "a reviewer"}`;
  if (fact.method === "rules") return "Found by rules (no AI)";
  return "Found by AI, quote checked";
}

type Props = {
  detail: CaseDetail;
  me: Me;
  onChange: () => Promise<void>;
  onShowDocument: (id: number, highlight?: string) => void;
};

// Each fact sits next to the exact sentence it came from. A fact whose quote didn't check out
// is shown as unverified, never as a fact. The reviewer can enter or correct any of them;
// the original answer is kept so corrections can be counted.
export function Facts({ detail, me, onChange, onShowDocument }: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  if (detail.extraction_status === "not_applicable") return null;
  const facts = detail.facts ?? [];
  const byField = new Map(facts.map((f) => [f.field, f]));
  const canEdit =
    (me.role === "nurse_reviewer" && detail.state === "in_nurse_review" && detail.assigned_to === me.username) ||
    (me.role === "medical_director" && detail.state === "escalated");

  return (
    <>
      <section className="card" data-testid="facts">
        <h2>Checklist facts</h2>
        {detail.extraction_status === "pending" && <p className="muted">Extraction is running. The case reaches the nurse queue when it finishes.</p>}
        {detail.extraction && detail.extraction.status !== "ok" && (
          <p className="small muted">Automatic extraction {detail.extraction.status === "timed_out" ? "timed out" : "failed"}, so facts need manual entry.</p>
        )}
        {detail.extraction_status === "manual_needed" && !detail.extraction && <p className="small muted">No automatic extraction for this case. Enter the facts from the documents.</p>}
        <ul className="plain">
          {(detail.checklist_fields ?? []).map((field) => {
            const f = byField.get(field.name);
            return (
              <li key={field.name} className={`fact ${f?.status ?? "missing"}`} data-testid={`fact-${field.name}`}>
                <div className="heading-row" style={{ marginBottom: 0 }}>
                  <strong>{field.label}</strong>
                  <span className={!f || f.status === "dropped" ? "badge risk-at_risk" : "badge"}>{valueText(f)}</span>
                </div>
                {f?.status === "verified" && f.quote && (
                  <>
                    <p className="quote">“{f.quote}”</p>
                    <p className="small muted">
                      {source(f)}
                      {f.document_id !== null && (
                        <>
                          {" · "}
                          <button type="button" className="link" onClick={() => onShowDocument(f.document_id as number, f.quote ?? undefined)}>
                            Show in document
                          </button>
                        </>
                      )}
                    </p>
                  </>
                )}
                {f?.status === "dropped" && <p className="small">Not shown as a fact: {f.note}. Check the documents and enter it yourself.</p>}
                {f?.status === "entered" && (
                  <p className="small muted">
                    {source(f)}
                    {f.note ? `: ${f.note}` : ""}
                  </p>
                )}
                {canEdit && editing !== field.name && (
                  <button type="button" className="link small" onClick={() => setEditing(field.name)}>
                    {f && f.status !== "dropped" ? "Correct" : "Enter"}
                  </button>
                )}
                {canEdit && editing === field.name && (
                  <FactForm caseId={detail.id} field={field} onDone={async () => { setEditing(null); await onChange(); }} onCancel={() => setEditing(null)} />
                )}
              </li>
            );
          })}
        </ul>
        {detail.extraction && detail.extraction.status === "ok" && (
          <p className="small muted">
            {detail.extraction.provider === "claude" ? `Model ${detail.extraction.model}` : "Rules baseline"} · {detail.extraction.verified} verified ·{" "}
            {detail.extraction.dropped} couldn&apos;t be verified · the AI never decides the case
          </p>
        )}
      </section>
      <SummaryPanel detail={detail} canEdit={canEdit} onChange={onChange} />
    </>
  );
}

function FactForm({
  caseId,
  field,
  onDone,
  onCancel,
}: {
  caseId: number;
  field: { name: string; label: string; kind: "integer" | "boolean" };
  onDone: () => Promise<void>;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(field.kind === "boolean" ? "unknown" : "");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  async function save() {
    try {
      await api(`/api/review/${caseId}/facts`, { method: "POST", body: { field: field.name, value: value || null, note } });
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save");
    }
  }

  return (
    <div className="stack" style={{ marginTop: 8 }}>
      {field.kind === "boolean" ? (
        <label>
          {field.label}
          <select value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="true">Yes</option>
            <option value="false">No</option>
            <option value="unknown">Not documented</option>
          </select>
        </label>
      ) : (
        <label>
          {field.label}
          <input inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Number, or leave empty if not documented" />
        </label>
      )}
      <label>
        Where in the documents
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: clinic note, history" />
      </label>
      <div className="buttons">
        <button type="button" onClick={save}>
          Save fact
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

function SummaryPanel({ detail, canEdit, onChange }: { detail: CaseDetail; canEdit: boolean; onChange: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const summary = detail.summary;
  if (!summary) return null;

  async function review(accepted: boolean) {
    try {
      await api(`/api/review/${detail.id}/summary`, { method: "POST", body: accepted ? { accepted } : { accepted, edited_text: text } });
      setEditing(false);
      await onChange();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save");
    }
  }

  return (
    <section className="card" data-testid="summary">
      <h2>Summary for the decision</h2>
      {summary.review_status === "edited" && summary.edited_text ? (
        <p>{summary.edited_text}</p>
      ) : (
        <ul>
          {summary.sentences.map((s, i) => (
            <li key={i}>{s.text}</li>
          ))}
        </ul>
      )}
      <p className="small muted">
        Built from the checked facts above, one sentence per fact.{" "}
        {summary.review_status === "pending" ? "Not reviewed yet." : `${summary.review_status === "accepted" ? "Accepted" : "Edited"} by ${summary.reviewed_by}.`}
      </p>
      {canEdit && summary.review_status === "pending" && !editing && (
        <div className="buttons">
          <button type="button" onClick={() => review(true)}>
            Accept summary
          </button>
          <button type="button" className="secondary" onClick={() => { setText(summary.text); setEditing(true); }}>
            Edit summary
          </button>
        </div>
      )}
      {editing && (
        <div className="stack">
          <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} aria-label="Edited summary" />
          <div className="buttons">
            <button type="button" onClick={() => review(false)}>
              Save edited summary
            </button>
            <button type="button" className="secondary" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {error && <p className="error small">{error}</p>}
    </section>
  );
}
