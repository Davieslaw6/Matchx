"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type Capabilities = {
  status: string;
  providers: string[];
  booking_code_generation_enabled: boolean;
  automated_wager_placement: boolean;
  reason: string;
  policy: string;
};

export default function BookingCodesPage() {
  const router = useRouter();
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then((session) => {
        if (session.status === 401) { router.replace("/login"); return null; }
        if (!session.ok) throw new Error("Could not verify owner session.");
        return fetch("/api/v1/booking-codes/capabilities", { credentials: "same-origin", signal: controller.signal });
      })
      .then(async (response) => {
        if (!response || controller.signal.aborted) return;
        if (response.status === 401) { router.replace("/login"); return; }
        const body = (await response.json()) as Capabilities & { message?: string };
        if (!response.ok) throw new Error(body.message || "Could not load provider capabilities.");
        setCapabilities(body);
      })
      .catch((cause: unknown) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [router]);

  return (
    <main className="dashboard">
      <header className="page-header"><div><p className="eyebrow">MATCH X / INTEGRATIONS</p><h1>Booking codes</h1></div><Link href="/tickets" className="text-link">Ticket manager</Link></header>
      <p className="page-intro">This feature requires a supported bookmaker/provider integration. MATCH X does not invent booking codes and never places wagers.</p>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      <section className="booking-unavailable">
        <p className="eyebrow">CAPABILITY STATUS</p>
        <h2>{capabilities?.status === "unavailable" ? "Provider not configured" : capabilities ? "Provider capability" : "Checking capability…"}</h2>
        <p>{capabilities?.reason ?? "Checking configured provider adapters."}</p>
        <ul><li>Code generation enabled: {capabilities ? (capabilities.booking_code_generation_enabled ? "Yes" : "No") : "—"}</li><li>Automated wager placement: {capabilities ? (capabilities.automated_wager_placement ? "Yes" : "No") : "—"}</li><li>Configured providers: {capabilities?.providers.length ? capabilities.providers.join(", ") : "None"}</li></ul>
        <p>{capabilities?.policy}</p>
        <p className="provenance">Blocked pending a supported provider adapter, credentials and terms/licensing review. No external booking code has been requested or fabricated.</p>
        <Link href="/tickets" className="text-link">Return to ticket drafts →</Link>
      </section>
    </main>
  );
}
