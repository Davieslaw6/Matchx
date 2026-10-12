"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Activity, Bot, CalendarDays, ChartNoAxesCombined, FileImage, ShieldAlert } from "lucide-react";

type Health = { status?: string; service?: string; readiness?: string };
type AuthStatus = "checking" | "authenticated" | "unavailable";

export default function HomePage() {
  const router = useRouter();
  const [authStatus, setAuthStatus] = useState<AuthStatus>("checking");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  async function signOut() {
    const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
    const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
    const response = await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    });
    if (response.ok) {
      router.replace("/login");
      router.refresh();
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 401) {
          router.replace("/login");
          return false;
        }
        if (!response.ok) throw new Error("Could not verify the owner session.");
        return true;
      })
      .then((authenticated) => {
        if (!authenticated || controller.signal.aborted) return;
        setAuthStatus("authenticated");
        return fetch("/api/v1/health/live", { signal: controller.signal })
          .then((response) => { if (!response.ok) throw new Error("API unavailable"); return response.json() as Promise<Health>; })
          .then(setHealth)
          .catch((error: unknown) => { if (error instanceof Error && error.name !== "AbortError") setHealthError(true); });
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== "AbortError") setAuthStatus("unavailable");
      });
    return () => controller.abort();
  }, [router]);

  if (authStatus === "checking") {
    return <main className="auth-shell"><p role="status">Checking owner session…</p></main>;
  }
  if (authStatus === "unavailable") {
    return <main className="auth-shell"><section className="auth-card"><h1>MATCH X</h1><p role="alert">Could not verify the owner session. Confirm the backend is running, then reload.</p><button onClick={() => window.location.reload()}>Retry</button></section></main>;
  }

  return <main className="dashboard">
    <header className="topbar"><div className="brand-mark" aria-hidden="true">MX</div><div><p className="eyebrow">PRIVATE FOOTBALL INTELLIGENCE</p><h1>MATCH X</h1></div>
      <div className="service-status" aria-live="polite"><span className={health?.status === "ok" ? "status-dot" : "status-dot status-offline"} />{healthError ? "API unavailable" : health?.status === "ok" ? "API connected" : "Connecting to API"}</div><button className="logout-button" type="button" onClick={() => void signOut()}>Sign out</button></header>
    <section className="hero"><p className="eyebrow">YOUR ANALYSIS WORKSPACE</p><h2>Understand the match.<br/><span>Measure the uncertainty.</span></h2><p className="hero-copy">Explore fixtures, compare statistical estimates with market prices, and keep every analysis grounded in traceable data.</p></section>
    <section aria-labelledby="workspace-heading"><div className="section-heading"><div><p className="eyebrow">WORKSPACE</p><h2 id="workspace-heading">Analysis tools</h2></div></div>
      <div className="tool-grid">
        <article className="tool-card"><CalendarDays/><h3>Match Explorer</h3><p>Find fixtures by date, competition, team and match status.</p><span className="coming-label">Imported data only</span><Link className="text-link" href="/explorer">Open explorer →</Link></article>
        <article className="tool-card"><ChartNoAxesCombined/><h3>Match Analysis</h3><p>Review stored model estimates, expected goals, scorelines and observed odds snapshots.</p><span className="coming-label">Stored predictions only</span><Link className="text-link" href="/explorer">Choose a fixture →</Link></article>
        <article className="tool-card"><Bot/><h3>AI Assistant</h3><p>Ask questions grounded in stored fixtures, team form and predictions.</p><span className="coming-label">Backend LLM key required</span><Link className="text-link" href="/chat">Open assistant →</Link></article>
        <article className="tool-card"><Activity/><h3>System status</h3><p>Backend liveness: {health?.status ?? (healthError ? "unavailable" : "checking")}.</p><span className="coming-label">Readiness checks available</span></article>
        <article className="tool-card"><CalendarDays/><h3>Ticket manager</h3><p>Build a draft from stored market odds, review snapshots and export CSV.</p><span className="coming-label">Preview + confirm required</span><Link className="text-link" href="/tickets">Open tickets →</Link></article>
        <article className="tool-card"><FileImage/><h3>Screenshot review</h3><p>Upload an image, extract OCR candidates and manually review the result.</p><span className="coming-label">No automatic odds writes</span><Link className="text-link" href="/imports">Open imports →</Link></article>
        <article className="tool-card"><ChartNoAxesCombined/><h3>Prediction history</h3><p>Track stored predictions against imported results using Brier score, log loss and top-outcome accuracy.</p><span className="coming-label">Post-match evaluation</span><Link className="text-link" href="/history">Open history →</Link></article>
        <article className="tool-card"><ShieldAlert/><h3>Booking codes</h3><p>Check whether a supported provider adapter is configured before requesting any code.</p><span className="coming-label">Provider unavailable</span><Link className="text-link" href="/booking-codes">Check status →</Link></article>
      </div></section><footer>Owner-only workspace · No automatic wager placement · No outcome guarantees</footer>
  </main>;
}
