"use client";

import { useEffect, useState } from "react";
import { api, ApiError, type CaseDetail, type Me } from "@/lib/api";

type Reason = { code: string; label: string };

// Shows only the buttons this person may use right now. The workflow service checks every
// rule again, so calling the API directly doesn't get around them.
export function Actions({ detail, me, onDone }: { detail: CaseDetail; me: Me; onDone: () => Promise<void> }) {
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const nurseCanPickUp = me.role === "nurse_reviewer" && detail.state === "ready_for_review";
  const nurseReviewing = me.role === "nurse_reviewer" && detail.state === "in_nurse_review" && detail.assigned_to === me.username;
  const directorDeciding = me.role === "medical_director" && detail.state === "escalated";
  const intakeCanWithdraw =
    me.role === "intake_coordinator" && ["received", "pended", "ready_for_review"].includes(detail.state);

  useEffect(() => {
    if (directorDeciding) void api<Reason[]>("/api/reason-codes").then(setReasons);
  }, [directorDeciding]);

  async function act(action: string, body: Record<string, unknown> = {}) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/cases/${detail.id}/${action}`, { method: "POST", body });
      setNote("");
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "That didn't work");
    } finally {
      setBusy(false);
    }
  }

  if (!nurseCanPickUp && !nurseReviewing && !directorDeciding && !intakeCanWithdraw) {
    const why =
      detail.state === "in_nurse_review" && me.role === "nurse_reviewer"
        ? `Being reviewed by ${detail.assigned_to}.`
        : `Nothing for you to do on this case right now.`;
    return (
      <section className="card">
        <h2>Your next step</h2>
        <p className="muted">{why}</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>Your next step</h2>
      {nurseCanPickUp && (
        <button type="button" disabled={busy} onClick={() => act("start_review")}>
          Pick up for review
        </button>
      )}

      {(nurseReviewing || directorDeciding || intakeCanWithdraw) && (
        <form onSubmit={(e) => e.preventDefault()}>
          {directorDeciding && (
            <label>
              Denial reason (needed to deny)
              <select value={reason} onChange={(e) => setReason(e.target.value)}>
                <option value="">Choose a reason</option>
                {reasons.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            {nurseReviewing ? "Note (needed to escalate)" : directorDeciding ? "Explanation (needed to deny)" : "Reason for withdrawing"}
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </label>
          <div className="buttons">
            {(nurseReviewing || directorDeciding) && (
              <button type="button" disabled={busy} onClick={() => act("approve")}>
                Approve
              </button>
            )}
            {nurseReviewing && (
              <button type="button" className="secondary" disabled={busy} onClick={() => act("escalate", { note })}>
                Escalate to medical director
              </button>
            )}
            {directorDeciding && (
              <button type="button" className="danger" disabled={busy} onClick={() => act("deny", { note, reason_code: reason || null })}>
                Deny
              </button>
            )}
            {intakeCanWithdraw && (
              <button type="button" className="secondary" disabled={busy} onClick={() => act("withdraw", { note })}>
                Withdraw request
              </button>
            )}
          </div>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {nurseReviewing && <p className="muted small">Only a medical director can deny. If this doesn&apos;t clearly meet the checklist, escalate it.</p>}
    </section>
  );
}
