"use client";

import { useEffect, useState } from "react";
import { Activity, Bot, CalendarDays, ChartNoAxesCombined } from "lucide-react";

type Health = { status?: string; service?: string; readiness?: string };

export default function HomePage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/health/live", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        return response.json() as Promise<Health>;
      })
      .then(setHealth)
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== "AbortError") setHealthError(true);
      });
    return () => controller.abort();
  }, []);

  return (
    <main className="dashboard">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">MX</div>
        <div><p className="eyebrow">PRIVATE FOOTBALL INTELLIGENCE</p><h1>MATCH X</h1></div>
        <div className="service-status" aria-live="polite">
          <span className={health?.status === "ok" ? "status-dot" : "status-dot status-offline"} />
          {healthError ? "API unavailable" : health?.status === "ok" ? "API connected" : "Connecting to API"}
        </div>
      </header>

      <section className="hero">
        <p className="eyebrow">YOUR ANALYSIS WORKSPACE</p>
        <h2>Understand the match.<br /><span>Measure the uncertainty.</span></h2>
        <p className="hero-copy">Explore fixtures, compare statistical estimates with market prices, and keep every analysis grounded in traceable data.</p>
      </section>

      <section aria-labelledby="workspace-heading">
        <div className="section-heading"><div><p className="eyebrow">WORKSPACE</p><h2 id="workspace-heading">Analysis tools</h2></div></div>
        <div className="tool-grid">
          <article className="tool-card"><CalendarDays /><h3>Match Explorer</h3><p>Find fixtures by date, competition, team and match status.</p><span className="coming-label">Data adapter pending</span></article>
          <article className="tool-card"><ChartNoAxesCombined /><h3>Match Analysis</h3><p>Review form, model estimates, market prices and missing data.</p><span className="coming-label">Prediction engine pending</span></article>
          <article className="tool-card"><Bot /><h3>AI Assistant</h3><p>Ask questions grounded in the application’s verified data.</p><span className="coming-label">LLM setup pending</span></article>
          <article className="tool-card"><Activity /><h3>System status</h3><p>Backend liveness: {health?.status ?? (healthError ? "unavailable" : "checking")}.</p><span className="coming-label">Readiness probes pending</span></article>
        </div>
      </section>
      <footer>Owner-only workspace · No automatic wager placement · No outcome guarantees</footer>
    </main>
  );
}
