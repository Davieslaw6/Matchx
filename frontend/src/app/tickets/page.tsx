"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type TicketSummary = { id: string; name: string; status: string; notes: string | null; selection_count: number; updated_at: string };
type Selection = { id: string; fixture_id: string; competition: string; home_team: string; away_team: string; match_date: string | null; kickoff_at: string | null; market: string; outcome: string; odds_snapshot: string; bookmaker: string | null; metadata: Record<string, string> };
type Revision = { revision: number; actor: string; before_state: Record<string, unknown>; after_state: Record<string, unknown>; created_at: string };
type TicketDetail = { id: string; name: string; status: string; notes: string | null; selection_count: number; combined_decimal_odds: string; selections: Selection[]; revisions: Revision[] };
type PendingAction = { action: string; token: string; idempotencyKey: string; summary: string; warnings: string[] };
type ApiError = { message?: string; detail?: { message?: string } };

export default function TicketsPage() {
  const router = useRouter();
  const [tickets, setTickets] = useState<TicketSummary[]>([]);
  const [selected, setSelected] = useState<TicketDetail | null>(null);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadTickets = useCallback(async () => {
    const response = await fetch("/api/v1/tickets", { credentials: "same-origin" });
    if (response.status === 401) { router.replace("/login"); return; }
    const body = (await response.json()) as { items?: TicketSummary[]; message?: string };
    if (!response.ok) throw new Error(body.message || "Could not load tickets.");
    setTickets(body.items ?? []);
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then((response) => {
        if (response.status === 401) { router.replace("/login"); return false; }
        if (!response.ok) throw new Error("Could not verify owner session.");
        return true;
      })
      .then((authenticated) => { if (authenticated && !controller.signal.aborted) void loadTickets().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not load tickets.")); })
      .catch((cause: unknown) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [loadTickets, router]);

  async function openTicket(id: string) {
    setError("");
    const response = await fetch(`/api/v1/tickets/${encodeURIComponent(id)}`, { credentials: "same-origin" });
    const body = (await response.json()) as TicketDetail & ApiError;
    if (response.status === 401) { router.replace("/login"); return; }
    if (!response.ok) throw new Error(body.detail?.message || body.message || "Could not open ticket.");
    setSelected(body);
  }

  async function previewAction(action: string, payload: Record<string, unknown>) {
    setError("");
    const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
    const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
    if (!csrfToken) throw new Error("CSRF token missing. Sign in again.");
    const response = await fetch("/api/v1/tickets/preview", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ action, payload }),
    });
    const body = (await response.json()) as { confirmation_token?: string; idempotency_key?: string; preview?: { summary?: string; warnings?: string[] }; detail?: ApiError["detail"]; message?: string };
    if (response.status === 401) { router.replace("/login"); return; }
    if (!response.ok || !body.confirmation_token || !body.idempotency_key) throw new Error(body.detail?.message || body.message || "Could not preview ticket action.");
    setPending({ action, token: body.confirmation_token, idempotencyKey: body.idempotency_key, summary: body.preview?.summary ?? "Confirm ticket action", warnings: body.preview?.warnings ?? [] });
  }

  async function confirmAction() {
    if (!pending) return;
    setLoading(true);
    setError("");
    try {
      const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
      const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
      const response = await fetch("/api/v1/tickets/confirm", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, "Idempotency-Key": pending.idempotencyKey },
        body: JSON.stringify({ confirmation_token: pending.token }),
      });
      const body = (await response.json()) as { ticket_id?: string; detail?: ApiError["detail"]; message?: string };
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) throw new Error(body.detail?.message || body.message || "Ticket action was not confirmed.");
      setPending(null);
      await loadTickets();
      if (body.ticket_id) await openTicket(body.ticket_id);
      else if (selected) await openTicket(selected.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ticket action failed.");
    } finally {
      setLoading(false);
    }
  }

  async function createTicket(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { await previewAction("create_ticket", { name, notes: notes || null }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not preview ticket."); }
  }

  async function requestRemove(selection: Selection) {
    if (!selected) return;
    try { await previewAction("remove_selection", { ticket_id: selected.id, selection_id: selection.id }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not preview removal."); }
  }

  async function requestArchive() {
    if (!selected) return;
    try { await previewAction("archive_ticket", { ticket_id: selected.id }); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not preview archive."); }
  }

  return (
    <main className="dashboard">
      <header className="page-header"><div><p className="eyebrow">MATCH X / WORKSPACE</p><h1>Ticket manager</h1></div><Link href="/explorer" className="text-link">Match explorer</Link></header>
      <p className="page-intro">Tickets are private analysis drafts. Every mutation requires preview and explicit confirmation. MATCH X never places a wager.</p>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {pending ? <section className="confirmation-panel" aria-live="polite"><p className="eyebrow">CONFIRMATION REQUIRED</p><h2>{pending.summary}</h2>{pending.warnings.map((warning) => <p key={warning}>{warning}</p>)}<p>This signed confirmation expires shortly. Nothing changes until you confirm.</p><div className="confirmation-actions"><button type="button" disabled={loading} onClick={() => void confirmAction()}>Confirm action</button><button type="button" className="secondary-button" disabled={loading} onClick={() => setPending(null)}>Cancel</button></div></section> : null}
      <div className="ticket-layout">
        <section className="ticket-sidebar">
          <h2>Draft tickets</h2>
          {tickets.length === 0 ? <p className="empty-copy">No tickets yet.</p> : tickets.map((ticket) => <button type="button" className={selected?.id === ticket.id ? "ticket-list-item selected" : "ticket-list-item"} key={ticket.id} onClick={() => void openTicket(ticket.id).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not open ticket."))}><strong>{ticket.name}</strong><span>{ticket.selection_count} selections · {ticket.status}</span></button>)}
          <form className="ticket-create-form" onSubmit={createTicket}><h3>Create ticket</h3><label htmlFor="ticket-name">Name</label><input id="ticket-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={160} required /><label htmlFor="ticket-notes">Notes (optional)</label><textarea id="ticket-notes" value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} maxLength={2000} /><button type="submit" disabled={loading || !name.trim()}>Preview creation</button></form>
        </section>
        <section className="ticket-detail">
          {!selected ? <div className="empty-state"><h2>Select a ticket</h2><p>Or create a draft using the form.</p></div> : <>
            <div className="ticket-detail-header"><div><p className="eyebrow">{selected.status.toUpperCase()}</p><h2>{selected.name}</h2><p>{selected.notes || "No notes."}</p></div><div className="ticket-header-actions"><a href={`/api/v1/tickets/${encodeURIComponent(selected.id)}/export.csv`} className="text-link">Export CSV</a>{selected.status === "draft" ? <button type="button" className="secondary-button" onClick={() => void requestArchive()}>Preview archive</button> : null}</div></div>
            <div className="ticket-stats"><div><span>Selections</span><strong>{selected.selection_count}</strong></div><div><span>Combined decimal odds</span><strong>{selected.combined_decimal_odds}</strong></div><div><span>Ticket ID</span><strong className="id-value">{selected.id}</strong></div></div>
            {selected.selections.length === 0 ? <div className="empty-state"><h3>No selections yet</h3><p>Open a fixture analysis page and add a stored odds snapshot to this draft.</p><Link href="/explorer" className="text-link">Find a fixture →</Link></div> : <div className="ticket-selections">{selected.selections.map((selection) => <article className="ticket-selection" key={selection.id}><div><p className="eyebrow">{selection.competition} · {selection.match_date ?? "Date unavailable"}</p><h3>{selection.home_team} vs {selection.away_team}</h3><p>{selection.market} / {selection.outcome} · {selection.bookmaker ?? "Bookmaker unavailable"}</p><span>Snapshot odds {selection.odds_snapshot} · {selection.metadata.observed_at ?? "Observation time unavailable"}</span></div>{selected.status === "draft" ? <button type="button" className="secondary-button" onClick={() => void requestRemove(selection)}>Preview remove</button> : null}</article>)}</div>}
            <section className="ticket-revisions"><h3>Revision history</h3>{selected.revisions.length === 0 ? <p>No revisions recorded.</p> : selected.revisions.map((revision) => <article key={revision.revision}><strong>Revision {revision.revision}</strong><span>{revision.actor} · {new Date(revision.created_at).toLocaleString()}</span></article>)}</section>
          </>}
        </section>
      </div>
    </main>
  );
}
