"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type CaseDetail } from "@/lib/api";
import { EVENT_LABEL, formatTime, hoursLeftText, RISK_LABEL, STATE_LABEL } from "@/lib/labels";
import { useSession } from "../../session";
import { Actions } from "./actions";
import { Facts } from "./facts";

type Doc = { id: number; title: string; doc_type: string; text: string };

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const { me } = useSession();
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [openDoc, setOpenDoc] = useState<Doc | null>(null);

  const load = useCallback(async () => {
    try {
      setDetail(await api<CaseDetail>(`/api/cases/${id}`));
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load the case");
    }
  }, [id]);

  useEffect(() => {
    if (me) void load();
  }, [me, load]);

  async function showDocument(documentId: number) {
    setOpenDoc(await api<Doc>(`/api/cases/${id}/documents/${documentId}`));
  }

  if (!me) return null;
  if (error && !detail) {
    return (
      <div className="card">
        <p className="error">{error}</p>
        <Link href="/">Back to my queue</Link>
      </div>
    );
  }
  if (!detail) return <p className="muted">Loading…</p>;

  return (
    <>
      <p>
        <Link href="/">← My queue</Link>
      </p>
      <div className="heading-row">
        <div>
          <h1>
            Case #{detail.id}: {detail.service.name}
          </h1>
          <p className="muted">
            {detail.member.name} ({detail.member.id}) · requested by {detail.provider.name || "provider"} (NPI{" "}
            {detail.provider.npi})
          </p>
        </div>
        <div className="status-box">
          <span className={`badge state-${detail.state}`} data-testid="case-state">
            {STATE_LABEL[detail.state]}
          </span>
          <span className={`badge risk-${detail.risk}`}>{RISK_LABEL[detail.risk]}</span>
          <span className="muted small">{hoursLeftText(detail.hours_left)}</span>
        </div>
      </div>

      <div className="two-columns">
        <div className="stack">
          <section className="card">
            <h2>Request</h2>
            <dl className="facts-list">
              <dt>Priority</dt>
              <dd>{detail.priority === "expedited" ? "Expedited (72 hours)" : "Standard (7 days)"}</dd>
              <dt>Service</dt>
              <dd>
                {detail.service.code} · {detail.service.name}
              </dd>
              <dt>Diagnoses</dt>
              <dd>{detail.diagnosis_codes.join(", ")}</dd>
              <dt>Service date</dt>
              <dd>{detail.service_date_start}</dd>
              <dt>Received</dt>
              <dd>{formatTime(detail.received_at)}</dd>
              <dt>Due</dt>
              <dd>{formatTime(detail.due_at)}</dd>
              <dt>Came in by</dt>
              <dd>{detail.submissions.map((s) => s.source.toUpperCase()).join(", ")}</dd>
              <dt>Checked against</dt>
              <dd>Catalogue {detail.catalogue_version}</dd>
            </dl>
            {detail.closed_reason && <p className="note">{detail.closed_reason}</p>}
            {detail.escalation_note && (
              <p className="note">
                <strong>Escalation note:</strong> {detail.escalation_note}
              </p>
            )}
            {detail.decision && (
              <div className="note" data-testid="decision">
                <strong>
                  {detail.state === "denied" ? "Denied" : "Approved"} by {detail.decision.by}
                  {detail.decision.at ? ` on ${formatTime(detail.decision.at)}` : ""}
                </strong>
                {detail.decision.reason && <p>Reason: {detail.decision.reason}</p>}
                {detail.decision.explanation && <p>{detail.decision.explanation}</p>}
              </div>
            )}
          </section>

          {detail.missing.length > 0 && (
            <section className="card warn" data-testid="missing">
              <h2>Waiting for documents</h2>
              <p className="small">One request went to the provider listing everything missing:</p>
              <ul>
                {detail.missing.map((m) => (
                  <li key={m.type}>{m.label}</li>
                ))}
              </ul>
            </section>
          )}

          <Actions detail={detail} me={me} onDone={load} />
        </div>

        <div className="stack">
          <Facts detail={detail} me={me} onChange={load} onShowDocument={showDocument} />

          <section className="card">
            <h2>Documents</h2>
            {detail.documents.length === 0 && <p className="muted">None yet.</p>}
            <ul className="plain">
              {detail.documents.map((d) => (
                <li key={d.id}>
                  <button type="button" className="link" onClick={() => showDocument(d.id)}>
                    {d.title}
                  </button>{" "}
                  <span className="muted small">{d.doc_type.replaceAll("_", " ")}</span>
                </li>
              ))}
            </ul>
            {openDoc && (
              <div className="doc-view" data-testid="document-view">
                <div className="heading-row">
                  <strong>{openDoc.title}</strong>
                  <button type="button" className="link" onClick={() => setOpenDoc(null)}>
                    Close
                  </button>
                </div>
                <pre>{openDoc.text}</pre>
              </div>
            )}
          </section>

          <section className="card">
            <h2>History</h2>
            <ol className="timeline" data-testid="history">
              {detail.history.map((e, i) => (
                <li key={i}>
                  <span className="muted small">{formatTime(e.at)}</span> <strong>{e.actor}</strong>{" "}
                  {EVENT_LABEL[e.event] ?? e.event.replaceAll("_", " ")}
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </>
  );
}
