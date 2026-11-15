"use client";

import type { CaseDetail, Me } from "@/lib/api";

// Step 5: a placeholder that says how facts will be gathered. Step 10 fills it with
// extracted facts and their quotes; Step 11 adds the drafted summary.
export function Facts({ detail }: { detail: CaseDetail; me: Me; onChange: () => Promise<void>; onShowDocument: (id: number) => void }) {
  if (detail.extraction_status === "not_applicable") return null;
  return (
    <section className="card">
      <h2>Checklist facts</h2>
      <p className="muted">
        {detail.extraction_status === "manual_needed"
          ? "No automatic extraction yet. Read the documents and record the checklist facts in your review."
          : "Facts will appear here once the documents are complete."}
      </p>
    </section>
  );
}
