"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

type Detail = {
  id: string;
  competition: string;
  home_team: string;
  away_team: string;
  match_date: string | null;
  kickoff_at: string | null;
  status: string;
  venue: string | null;
  result: { home_goals: number; away_goals: number; source: string } | null;
  prediction: {
    model_version: string;
    data_cutoff_at: string;
    created_at: string;
    probabilities: {
      home_win: number;
      draw: number;
      away_win: number;
      over: Record<string, number>;
      btts_yes: number;
      btts_no: number;
      correct_scores: { home_goals: number; away_goals: number; probability: number }[];
    };
    feature_snapshot: {
      home_xg: number;
      away_xg: number;
      rho: number;
      home_advantage: number;
      training_matches: number;
      time_decay_days: number;
      data_hash: string;
      retained_scoreline_mass: number;
    };
  } | null;
  odds: { provider: string; bookmaker: string | null; market: string; outcome: string; decimal_odds: number; observed_at: string }[];
};
type ApiError = { message?: string };

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function AnalysisPage() {
  const params = useParams<{ fixtureId: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/v1/fixtures/${encodeURIComponent(params.fixtureId)}`, {
      credentials: "same-origin", signal: controller.signal,
    }).then(async (response) => {
      if (response.status === 401) {
        router.replace("/login");
        return null;
      }
      if (!response.ok) {
        const body = (await response.json()) as ApiError;
        throw new Error(body.message || "Could not load match analysis.");
      }
      return (await response.json()) as Detail;
    }).then((value) => {
      if (value) setDetail(value);
    }).catch((cause: unknown) => {
      if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [params.fixtureId, router]);

  return (
    <main className="dashboard">
      <header className="page-header">
        <div><p className="eyebrow">MATCH X / ANALYSIS</p><h1>Match analysis</h1></div>
        <Link href="/explorer" className="text-link">Back to explorer</Link>
      </header>
      {loading ? <p className="empty-state">Loading match data…</p> : null}
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {detail ? <>
        <section className="analysis-match">
          <p className="eyebrow">{detail.competition} · {detail.status}</p>
          <h2>{detail.home_team} <span>vs</span> {detail.away_team}</h2>
          <p>{detail.match_date ?? "Match date unavailable"}{detail.kickoff_at ? ` · ${new Date(detail.kickoff_at).toLocaleString()}` : " · Kickoff time unavailable"}</p>
          {detail.venue ? <p>Venue: {detail.venue}</p> : null}
          {detail.result ? <p className="result-score">Final score: {detail.result.home_goals}–{detail.result.away_goals}</p> : null}
        </section>
        {!detail.prediction ? <section className="empty-state"><h2>No stored prediction</h2><p>A prediction is shown only after a model run stores it for this fixture. The page will not invent one on demand.</p></section> : <>
          <section className="analysis-section">
            <div className="section-heading"><div><p className="eyebrow">M1 / DIXON–COLES</p><h2>1X2 probability estimates</h2></div></div>
            <div className="probability-grid">
              {[
                ["Home win", detail.prediction.probabilities.home_win],
                ["Draw", detail.prediction.probabilities.draw],
                ["Away win", detail.prediction.probabilities.away_win],
              ].map(([label, value]) => <article className="probability-card" key={String(label)}>
                <span>{label}</span><strong>{percent(Number(value))}</strong>
                <div className="probability-track"><span style={{ width: percent(Number(value)) }} /></div>
              </article>)}
            </div>
          </section>
          <section className="analysis-section">
            <div className="section-heading"><div><p className="eyebrow">MODEL FEATURES</p><h2>Expected goals and diagnostics</h2></div></div>
            <div className="diagnostic-grid">
              <article className="diagnostic-card"><span>{detail.home_team} xG</span><strong>{detail.prediction.feature_snapshot.home_xg.toFixed(2)}</strong></article>
              <article className="diagnostic-card"><span>{detail.away_team} xG</span><strong>{detail.prediction.feature_snapshot.away_xg.toFixed(2)}</strong></article>
              <article className="diagnostic-card"><span>Training matches</span><strong>{detail.prediction.feature_snapshot.training_matches}</strong></article>
              <article className="diagnostic-card"><span>Time decay</span><strong>{detail.prediction.feature_snapshot.time_decay_days} days</strong></article>
              <article className="diagnostic-card"><span>Rho</span><strong>{detail.prediction.feature_snapshot.rho.toFixed(3)}</strong></article>
              <article className="diagnostic-card"><span>Retained score mass</span><strong>{percent(detail.prediction.feature_snapshot.retained_scoreline_mass)}</strong></article>
            </div>
            <p className="provenance">Model: {detail.prediction.model_version} · Data cutoff: {new Date(detail.prediction.data_cutoff_at).toLocaleString()} · Dataset SHA-256: {detail.prediction.feature_snapshot.data_hash}</p>
          </section>
          <section className="analysis-section">
            <div className="section-heading"><div><p className="eyebrow">SCORELINES</p><h2>Highest-probability scorelines</h2></div></div>
            <div className="scoreline-grid">
              {detail.prediction.probabilities.correct_scores.map((score) => <article className="scoreline-card" key={`${score.home_goals}-${score.away_goals}`}>
                <strong>{score.home_goals}–{score.away_goals}</strong><span>{percent(score.probability)}</span>
              </article>)}
            </div>
            <p className="provenance">BTTS Yes {percent(detail.prediction.probabilities.btts_yes)} · BTTS No {percent(detail.prediction.probabilities.btts_no)} · Over 2.5 {percent(detail.prediction.probabilities.over["2.5"] ?? 0)}</p>
          </section>
        </>}
        <section className="analysis-section">
          <div className="section-heading"><div><p className="eyebrow">OBSERVED DATA</p><h2>Odds snapshots</h2></div></div>
          {detail.odds.length === 0 ? <p className="empty-state">No odds snapshots are stored for this fixture.</p> : <div className="odds-table">
            {detail.odds.map((odd, index) => <article className="odds-row" key={`${odd.provider}-${odd.bookmaker}-${odd.market}-${odd.outcome}-${odd.observed_at}-${index}`}>
              <span>{odd.market} / {odd.outcome}</span><strong>{odd.decimal_odds.toFixed(2)}</strong>
              <span>{odd.bookmaker ?? odd.provider}</span><time>{new Date(odd.observed_at).toLocaleString()}</time>
            </article>)}
          </div>}
        </section>
        <p className="responsible-note">Probabilities are model estimates, not guarantees. Historical calibration does not establish future profitability. No wager is placed by this application.</p>
      </> : null}
    </main>
  );
}
