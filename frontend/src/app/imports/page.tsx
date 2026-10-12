"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ChangeEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type OddsCandidate = { line_number: number; line: string; numeric_candidates: number[]; status: string };
type MatchCandidate = { line: string; home_candidate: string; away_candidate: string };
type ScreenshotImport = {
  id: string; filename: string; mime_type: string; sha256_prefix: string; byte_size: number;
  status: string; parsed_data: { odds_candidates?: OddsCandidate[]; match_candidates?: MatchCandidate[]; limitations?: string[] };
  error_message: string | null; created_at: string; reviewed_at: string | null; review_notes: string | null; ocr_text?: string;
};
type ApiError = { message?: string; detail?: { message?: string } };

export default function ScreenshotImportsPage() {
  const router = useRouter();
  const [items, setItems] = useState<ScreenshotImport[]>([]);
  const [selected, setSelected] = useState<ScreenshotImport | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadImports = useCallback(async () => {
    const response = await fetch("/api/v1/imports/screenshots", { credentials: "same-origin" });
    if (response.status === 401) { router.replace("/login"); return; }
    const body = (await response.json()) as { items?: ScreenshotImport[]; message?: string };
    if (!response.ok) throw new Error(body.message || "Could not load screenshot imports.");
    setItems(body.items ?? []);
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then((response) => {
        if (response.status === 401) { router.replace("/login"); return false; }
        if (!response.ok) throw new Error("Could not verify owner session.");
        return true;
      })
      .then((authenticated) => { if (authenticated && !controller.signal.aborted) void loadImports().catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not load imports.")); })
      .catch((cause: unknown) => { if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message); });
    return () => controller.abort();
  }, [loadImports, router]);

  async function openImport(id: string) {
    setError("");
    const response = await fetch(`/api/v1/imports/screenshots/${encodeURIComponent(id)}`, { credentials: "same-origin" });
    const body = (await response.json()) as ScreenshotImport & ApiError;
    if (response.status === 401) { router.replace("/login"); return; }
    if (!response.ok) throw new Error(body.detail?.message || body.message || "Could not open import.");
    setSelected(body);
    setReviewNotes(body.review_notes ?? "");
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
      const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
      if (!csrfToken) throw new Error("CSRF token missing. Sign in again.");
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/v1/imports/screenshots", {
        method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrfToken }, body: form,
      });
      const body = (await response.json()) as ScreenshotImport & ApiError;
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) throw new Error(body.detail?.message || body.message || "Upload failed.");
      setSelected(body); setFile(null);
      const picker = document.getElementById("screenshot-file") as HTMLInputElement | null;
      if (picker) picker.value = "";
      setNotice(body.error_message || "Original image stored. Review extracted text before using any values.");
      await loadImports();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  async function review(decision: "accept" | "reject") {
    if (!selected || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
      const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
      const response = await fetch(`/api/v1/imports/screenshots/${encodeURIComponent(selected.id)}/review`, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify({ decision, notes: reviewNotes || null }),
      });
      const body = (await response.json()) as ScreenshotImport & ApiError;
      if (response.status === 401) { router.replace("/login"); return; }
      if (!response.ok) throw new Error(body.detail?.message || body.message || "Review update failed.");
      setSelected(body);
      setNotice(decision === "accept" ? "Marked reviewed. No odds, ticket or wager was created." : "Screenshot rejected. Original retained for audit.");
      await loadImports();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Review update failed.");
    } finally {
      setBusy(false);
    }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  return (
    <main className="dashboard">
      <header className="page-header"><div><p className="eyebrow">MATCH X / IMPORTS</p><h1>Screenshot review</h1></div><Link href="/explorer" className="text-link">Match explorer</Link></header>
      <p className="page-intro">Upload a PNG, JPEG or WEBP screenshot up to 5 MiB. OCR candidates are untrusted and never create odds, selections or wagers automatically.</p>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      {notice ? <p className="ticket-notice" role="status">{notice}</p> : null}
      <form className="screenshot-upload" onSubmit={upload}><label htmlFor="screenshot-file">Screenshot image</label><input id="screenshot-file" type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseFile} required /><span>{file ? `${file.name} · ${Math.ceil(file.size / 1024)} KiB` : "The backend validates file signature, MIME type, pixel count and size."}</span><button type="submit" disabled={busy || !file}>{busy ? "Processing…" : "Upload and extract text"}</button></form>
      <div className="screenshot-layout">
        <aside className="screenshot-list"><h2>Recent imports</h2>{items.length === 0 ? <p className="empty-copy">No screenshots imported.</p> : items.map((item) => <button type="button" key={item.id} className={selected?.id === item.id ? "ticket-list-item selected" : "ticket-list-item"} onClick={() => void openImport(item.id).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Could not open import."))}><strong>{item.filename}</strong><span>{item.status} · {new Date(item.created_at).toLocaleString()}</span></button>)}</aside>
        <section className="screenshot-detail">
          {!selected ? <div className="empty-state"><h2>Select an import</h2><p>Uploaded images and OCR output are retained privately for manual review.</p></div> : <>
            <div className="screenshot-detail-header"><div><p className="eyebrow">{selected.status.toUpperCase()}</p><h2>{selected.filename}</h2><p>{selected.byte_size} bytes · SHA-256 {selected.sha256_prefix}…</p></div><a href={`/api/v1/imports/screenshots/${encodeURIComponent(selected.id)}/image`} target="_blank" rel="noreferrer" className="text-link">Open original image ↗</a></div>
            <div className="screenshot-image-frame"><img src={`/api/v1/imports/screenshots/${encodeURIComponent(selected.id)}/image`} alt={selected.filename} /></div>
            {selected.error_message ? <p className="inline-error">{selected.error_message}</p> : null}
            <section className="ocr-section"><h3>OCR text</h3><pre>{selected.ocr_text || "No OCR text was extracted. Review the original image manually."}</pre></section>
            <section className="ocr-section"><h3>Possible match lines</h3>{selected.parsed_data.match_candidates?.length ? selected.parsed_data.match_candidates.map((candidate, index) => <p key={`${candidate.line}-${index}`}>{candidate.home_candidate} vs {candidate.away_candidate} <span className="coming-label">Unverified</span></p>) : <p className="empty-copy">No match lines identified.</p>}</section>
            <section className="ocr-section"><h3>Possible odds numbers</h3>{selected.parsed_data.odds_candidates?.length ? selected.parsed_data.odds_candidates.map((candidate) => <article className="ocr-candidate" key={candidate.line_number}><span>Line {candidate.line_number}</span><strong>{candidate.numeric_candidates.join(" · ")}</strong><p>{candidate.line}</p><small>Unverified OCR candidate — no market/outcome assigned</small></article>) : <p className="empty-copy">No odds-like lines identified.</p>}</section>
            {selected.parsed_data.limitations?.map((limitation) => <p className="provenance" key={limitation}>{limitation}</p>)}
            {selected.status !== "reviewed" && selected.status !== "rejected" ? <section className="screenshot-review"><label htmlFor="review-notes">Review notes (optional)</label><textarea id="review-notes" value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} maxLength={2000} rows={3} /><div className="confirmation-actions"><button type="button" disabled={busy} onClick={() => void review("accept")}>Mark reviewed</button><button type="button" className="secondary-button" disabled={busy} onClick={() => void review("reject")}>Reject screenshot</button></div></section> : <p className="provenance">Reviewed {selected.reviewed_at ? new Date(selected.reviewed_at).toLocaleString() : ""}. Review status does not change football data.</p>}
          </>}
        </section>
      </div>
    </main>
  );
}
