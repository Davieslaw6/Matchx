"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type HistoryItem = {
  prediction_id: string; fixture_id: string; competition: string; home_team: string; away_team: string;
  kickoff_at: string | null; match_date: string | null; fixture_status: string; prediction_status: string;
  model_version: string; data_cutoff_at: string; created_at: string;
  probabilities: { home_win?: number; draw?: number; away_win?: number };
  result: { home_goals: number; away_goals: number } | null;
  evaluation: { status?: string; reason?: string; actual_outcome?: string; predicted_outcome?: string; brier_score?: number; log_loss?: number; top_outcome_correct?: boolean } | null;
};
type Summary = { evaluated_predictions: number; mean_brier_score: number | null; mean_log_loss: number | null; top_outcome_accuracy: number | null };
type ApiError = { message?: string; detail?: { message?: string } };

export default function HistoryPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadHistory = useCallback(async (requestedPage = 1) => {
    const response = await fetch(`/api/v1/history?page=${requestedPage}&page_size=20`, { credentials: "same-origin" });
    if (response.status === 401) { router.replace("/login"); return; }
    const body = (await response.json()) as { items?: HistoryItem[]; summary?: Summary; total?: number; message?: string };
    if (!response.ok) throw new Error(body.message || "Could not load prediction history.");
    setItems(body.items ?? []); setSummary(body.summary ?? null); setTotal(body.total ?? 0); setPage(requestedPage);
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then((response) => {
        if (response.status === 401) { router.replace("/login"); return false; }
        if (!response.ok) throw new Error("Could not verify owner session.");
        return true;
      })
      .then((authenticated) => { if (authenticated && !controller.signal.aborted) void loadHistory(1).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not load history.")); })
      .catch((cause: unknown) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [loadHistory, router]);

  async function evaluate() {
    setBusy(true); setError(""); setNotice("");
    try {
      const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
      const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
      if (!csrfToken) throw new Error("CSRF token missing. Sign in again.");
      const response = await fetch("/api/v1/history/evaluate", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ limit: 500 }),
      });
      const body = (await response.json()) as { result?: { evaluated?: number; skipped_invalid_probabilities?: number }; message?: string; detail?: ApiError["detail"] };
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) throw new Error(body.detail?.message || body.message || "Evaluation failed.");
      setNotice(`Evaluation complete: ${body.result?.evaluated ?? 0} valid predictions evaluated; ${body.result?.skipped_invalid_probabilities ?? 0} invalid snapshots recorded.`);
      await loadHistory(1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Evaluation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="dashboard">
      <header className="page-header"><div><p className="eyebrow">MATCH X / MODEL HISTORY</p><h1>Prediction history</h1></div><Link href="/explorer" className="text-link">Match explorer</Link></header>
      <p className="page-intro">Only stored pre-kickoff predictions with imported final results can be evaluated. Metrics are descriptive, not guarantees of future performance.</p>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {notice ? <p className="ticket-notice" role="status">{notice}</p> : null}
      <div className="history-toolbar"><div><h2>Out-of-sample record</h2><p>Evaluation is idempotent per prediction and records the data cutoff.</p></div><button type="button" disabled={busy} onClick={() => void evaluate()}>{busy ? "Evaluating…" : "Evaluate finished predictions"}</button></div>
      <div className="history-summary">
        <div><span>Evaluated predictions</span><strong>{summary?.evaluated_predictions ?? "—"}</strong></div>
        <div><span>Mean multiclass Brier (lower is better)</span><strong>{summary?.mean_brier_score == null ? "—" : summary.mean_brier_score.toFixed(4)}</strong></div>
        <div><span>Mean log loss (lower is better)</span><strong>{summary?.mean_log_loss == null ? "—" : summary.mean_log_loss.toFixed(4)}</strong></div>
        <div><span>Top-outcome accuracy</span><strong>{summary?.top_outcome_accuracy == null ? "—" : `${(summary.top_outcome_accuracy * 100).toFixed(1)}%`}</strong></div>
      </div>
      <section className="history-list">
        {items.length === 0 ? <div className="empty-state"><h2>No prediction history yet</h2><p>Generate stored predictions and import final results first.</p><Link href="/explorer" className="text-link">Explore fixtures →</Link></div> : items.map((item) => <article className="history-item" key={item.prediction_id}>
          <div className="history-item-header"><div><p className="eyebrow">{item.competition} · {item.match_date ?? "Date unavailable"}</p><h2>{item.home_team} vs {item.away_team}</h2></div><span className={item.evaluation ? "status-pill evaluated" : "status-pill"}>{item.evaluation ? item.evaluation.status === "invalid_probability_snapshot" ? "Invalid snapshot" : "Evaluated" : item.result ? "Result available" : item.fixture_status}</span></div>
          <div className="history-probabilities"><span>Home <strong>{item.probabilities.home_win == null ? "—" : `${(item.probabilities.home_win * 100).toFixed(1)}%`}</strong></span><span>Draw <strong>{item.probabilities.draw == null ? "—" : `${(item.probabilities.draw * 100).toFixed(1)}%`}</strong></span><span>Away <strong>{item.probabilities.away_win == null ? "—" : `${(item.probabilities.away_win * 100).toFixed(1)}%`}</strong></span></div>
          <div className="history-result-row"><span>Actual result: {item.result ? `${item.result.home_goals}–${item.result.away_goals}` : "Not imported"}</span><span>{item.evaluation?.status === "invalid_probability_snapshot" ? item.evaluation.reason : item.evaluation ? `Brier ${item.evaluation.brier_score?.toFixed(4)} · Log loss ${item.evaluation.log_loss?.toFixed(4)} · ${item.evaluation.top_outcome_correct ? "Correct top outcome" : "Incorrect top outcome"}` : "Not evaluated"}</span></div>
          <p className="provenance">Model {item.model_version} · Data cutoff {new Date(item.data_cutoff_at).toLocaleString()}</p>
          <Link href={`/analysis/${encodeURIComponent(item.fixture_id)}`} className="text-link">Open analysis →</Link>
        </article>)}
      </section>
      <div className="history-pagination"><button type="button" className="secondary-button" disabled={page <= 1} onClick={() => void loadHistory(page - 1)}>Previous</button><span>Page {page} · {total} predictions</span><button type="button" className="secondary-button" disabled={page * 20 >= total} onClick={() => void loadHistory(page + 1)}>Next</button></div>
    </main>
  );
}
