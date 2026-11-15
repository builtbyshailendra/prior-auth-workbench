"use client";

import type { CaseDetail, Fact, Me } from "@/lib/api";

function valueText(fact: Fact): string {
  if (fact.status === "not_documented") return "Not documented";
  if (fact.status === "dropped") return "Couldn't verify";
  if (fact.value === true) return "Yes";
  if (fact.value === false) return "No";
  return String(fact.value);
}

function source(fact: Fact): string {
  if (fact.method === "manual") return `Entered by ${fact.entered_by ?? "a reviewer"}`;
  if (fact.method === "rules") return "Found by rules (no AI)";
  return "Found by AI, quote checked";
}

// Each fact sits next to the exact sentence it came from. A fact whose quote didn't check out
// is shown as unverified, never as a fact.
export function Facts({
  detail,
  onShowDocument,
}: {
  detail: CaseDetail;
  me: Me;
  onChange: () => Promise<void>;
  onShowDocument: (id: number, highlight?: string) => void;
}) {
  if (detail.extraction_status === "not_applicable") return null;
  const facts = detail.facts ?? [];

  return (
    <section className="card" data-testid="facts">
      <h2>Checklist facts</h2>
      {detail.extraction_status === "pending" && <p className="muted">Extraction is running. The case reaches the nurse queue when it finishes.</p>}
      {detail.extraction_status === "manual_needed" && facts.length === 0 && (
        <p className="muted">No automatic extraction for this case. Read the documents and record the checklist facts in your review.</p>
      )}
      {detail.extraction && detail.extraction.status !== "ok" && (
        <p className="small muted">Automatic extraction {detail.extraction.status === "timed_out" ? "timed out" : "failed"}, so facts need manual entry.</p>
      )}
      <ul className="plain">
        {facts.map((f) => (
          <li key={f.id} className={`fact ${f.status}`} data-testid={`fact-${f.field}`}>
            <div className="heading-row" style={{ marginBottom: 0 }}>
              <strong>{f.label}</strong>
              <span className={f.status === "dropped" ? "badge risk-at_risk" : "badge"}>{valueText(f)}</span>
            </div>
            {f.status === "verified" && f.quote && (
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
            {f.status === "dropped" && <p className="small">Not shown as a fact: {f.note}. Check the documents and enter it yourself.</p>}
            {f.status === "entered" && (
              <p className="small muted">
                {source(f)}
                {f.note ? `: ${f.note}` : ""}
              </p>
            )}
          </li>
        ))}
      </ul>
      {detail.extraction && detail.extraction.status === "ok" && (
        <p className="small muted">
          {detail.extraction.provider === "claude" ? `Model ${detail.extraction.model}` : "Rules baseline"} · {detail.extraction.verified} verified ·{" "}
          {detail.extraction.dropped} couldn&apos;t be verified · the AI never decides the case
        </p>
      )}
    </section>
  );
}
