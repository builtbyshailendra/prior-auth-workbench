"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, type CaseSummary } from "@/lib/api";
import { hoursLeftText, RISK_LABEL, ROLE_LABEL, STATE_LABEL } from "@/lib/labels";
import { useSession } from "./session";

const QUEUE_INTRO: Record<string, string> = {
  intake_coordinator: "Requests coming in, waiting for documents, or closed at intake.",
  nurse_reviewer: "Cases ready for a nurse, and the ones you're reviewing. Earliest deadline first.",
  medical_director: "Cases escalated to a medical director, and the ones you decided.",
};

export default function QueuePage() {
  const { me } = useSession();
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [priority, setPriority] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!me || me.role === "admin") return;
    const query = priority ? `?priority=${priority}` : "";
    api<CaseSummary[]>(`/api/cases${query}`)
      .then(setCases)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load the queue"));
  }, [me, priority]);

  if (!me) return null;
  if (me.role === "admin") {
    return (
      <div className="card">
        <h1>Admin</h1>
        <p>Admins manage staff accounts and don't see cases.</p>
        <Link href="/admin/users">Manage users</Link>
      </div>
    );
  }

  return (
    <>
      <div className="heading-row">
        <div>
          <h1>My queue</h1>
          <p className="muted">
            {ROLE_LABEL[me.role]}: {QUEUE_INTRO[me.role]}
          </p>
        </div>
        <label className="inline">
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All</option>
            <option value="expedited">Expedited</option>
            <option value="standard">Standard</option>
          </select>
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {cases && cases.length === 0 && <p className="card muted">Nothing in your queue.</p>}
      {cases && cases.length > 0 && (
        <table className="queue">
          <thead>
            <tr>
              <th>Case</th>
              <th>Member</th>
              <th>Service</th>
              <th>Status</th>
              <th>Deadline</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.id} data-testid={`case-row-${c.id}`}>
                <td>
                  <Link href={`/cases/${c.id}`}>#{c.id}</Link>
                  {c.priority === "expedited" && <span className="tag expedited">Expedited</span>}
                </td>
                <td>
                  {c.member.name}
                  <div className="muted small">{c.member.id}</div>
                </td>
                <td>
                  {c.service.name}
                  <div className="muted small">{c.service.code}</div>
                </td>
                <td>
                  <span className={`badge state-${c.state}`}>{STATE_LABEL[c.state]}</span>
                  {c.rfi_count > 0 && <div className="muted small">{c.rfi_count} request(s) for documents</div>}
                </td>
                <td>
                  <span className={`badge risk-${c.risk}`}>{RISK_LABEL[c.risk]}</span>
                  <div className="muted small">{hoursLeftText(c.hours_left)}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
