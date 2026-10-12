"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type SyncRun = { job_name: string; provider: string; status: string; counts: Record<string, unknown>; error_summary: string | null; started_at: string | null; finished_at: string | null };
type Settings = {
  environment: string; database: string; owner_account_exists: boolean; session_cookie_secure: boolean; secrets_returned: boolean;
  providers: { football_data_org_configured: boolean; historical_csv_import: boolean; live_odds_provider_configured: boolean; booking_code_provider_configured: boolean };
  ai: { configured: boolean; model: string; requests_per_hour: number };
  ocr: { configured: boolean; supported_formats: string[]; max_image_bytes: number; max_pixels: number };
  recent_syncs: SyncRun[];
};

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then((session) => {
        if (session.status === 401) { router.replace("/login"); return null; }
        if (!session.ok) throw new Error("Could not verify owner session.");
        return fetch("/api/v1/settings", { credentials: "same-origin", signal: controller.signal });
      })
      .then(async (response) => {
        if (!response || controller.signal.aborted) return;
        if (response.status === 401) { router.replace("/login"); return; }
        const body = (await response.json()) as Settings & { message?: string };
        if (!response.ok) throw new Error(body.message || "Could not load settings.");
        setSettings(body);
      })
      .catch((cause: unknown) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [router]);

  const yesNo = (value: boolean) => value ? "Configured" : "Not configured";
  return (
    <main className="dashboard">
      <header className="page-header"><div><p className="eyebrow">MATCH X / SYSTEM</p><h1>Settings and status</h1></div><Link href="/" className="text-link">Dashboard</Link></header>
      <p className="page-intro">Runtime settings are environment-managed. Secret values are never returned by this page or the settings API.</p>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {!settings ? <p className="empty-copy">Loading system status…</p> : <>
        <div className="settings-summary">
          <article><span>Environment</span><strong>{settings.environment}</strong></article>
          <article><span>Database</span><strong>{settings.database}</strong></article>
          <article><span>Owner account</span><strong>{settings.owner_account_exists ? "Created" : "Missing"}</strong></article>
          <article><span>Secure session cookie</span><strong>{settings.session_cookie_secure ? "Enabled" : "Disabled in local development"}</strong></article>
        </div>
        <div className="settings-sections">
          <section className="settings-panel"><h2>Data providers</h2><div><span>football-data.org</span><strong>{yesNo(settings.providers.football_data_org_configured)}</strong></div><div><span>Historical football-data.co.uk CSV</span><strong>{yesNo(settings.providers.historical_csv_import)}</strong></div><div><span>Live odds</span><strong>{yesNo(settings.providers.live_odds_provider_configured)}</strong></div><div><span>Booking-code provider</span><strong>{yesNo(settings.providers.booking_code_provider_configured)}</strong></div><p className="provenance">Live odds and booking-code integrations are not configured. No live odds or booking codes are invented.</p></section>
          <section className="settings-panel"><h2>AI assistant</h2><div><span>Provider API key</span><strong>{yesNo(settings.ai.configured)}</strong></div><div><span>Model</span><strong>{settings.ai.model}</strong></div><div><span>Request limit</span><strong>{settings.ai.requests_per_hour} per hour</strong></div><p className="provenance">Set the API key in the backend environment; its value is never shown here.</p><Link href="/chat" className="text-link">Open assistant →</Link></section>
          <section className="settings-panel"><h2>Screenshot OCR</h2><div><span>Tesseract engine</span><strong>{yesNo(settings.ocr.configured)}</strong></div><div><span>Supported formats</span><strong>{settings.ocr.supported_formats.join(", ")}</strong></div><div><span>Image limit</span><strong>{Math.round(settings.ocr.max_image_bytes / 1024 / 1024)} MiB / {settings.ocr.max_pixels.toLocaleString()} pixels</strong></div><Link href="/imports" className="text-link">Review screenshots →</Link></section>
        </div>
        <section className="settings-panel settings-syncs"><h2>Recent data sync jobs</h2>{settings.recent_syncs.length === 0 ? <p className="empty-copy">No sync jobs recorded.</p> : settings.recent_syncs.map((run, index) => <article key={`${run.job_name}-${run.started_at}-${index}`}><div><strong>{run.job_name}</strong><span>{run.provider} · {run.status}</span></div><span>{run.started_at ? new Date(run.started_at).toLocaleString() : "Start time unavailable"}</span>{run.error_summary ? <p>{run.error_summary}</p> : null}</article>)}</section>
      </>}
    </main>
  );
}
