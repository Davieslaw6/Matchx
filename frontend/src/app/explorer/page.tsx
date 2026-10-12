"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import { formatKickoff } from "@/lib/format";
import { useRouter } from "next/navigation";

type Fixture = {
  id: string;
  competition: string;
  home_team: string;
  away_team: string;
  match_date: string | null;
  kickoff_at: string | null;
  status: string;
  prediction_available: boolean;
};
type FixturePage = { items: Fixture[]; page: number; page_size: number; total: number };
type ApiError = { message?: string };
type Filters = { startDate: string; endDate: string; team: string; status: string };

export default function ExplorerPage() {
  const router = useRouter();
  const [data, setData] = useState<FixturePage | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [team, setTeam] = useState("");
  const [status, setStatus] = useState("");
  const [applied, setApplied] = useState<Filters>({ startDate: "", endDate: "", team: "", status: "" });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    if (applied.startDate) params.set("start_date", applied.startDate);
    if (applied.endDate) params.set("end_date", applied.endDate);
    if (applied.team.trim()) params.set("team", applied.team.trim());
    if (applied.status) params.set("status", applied.status);
    try {
      const response = await fetch(`/api/v1/fixtures?${params.toString()}`, {
        credentials: "same-origin",
        signal,
      });
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) {
        const body = (await response.json()) as ApiError;
        throw new Error(body.message || "Could not load fixtures.");
      }
      setData((await response.json()) as FixturePage);
    } catch (cause) {
      if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [applied, page, router]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setApplied({ startDate, endDate, team, status });
  }

  return (
    <main className="dashboard">
      <header className="page-header">
        <div><p className="eyebrow">MATCH X / WORKSPACE</p><h1>Match Explorer</h1></div>
        <Link href="/" className="text-link">Back to workspace</Link>
      </header>
      <p className="page-intro">Browse imported fixtures. No demo fixtures are shown as real data.</p>
      <form className="filter-panel" onSubmit={applyFilters}>
        <div className="filter-field"><label htmlFor="start-date">From date</label><input id="start-date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></div>
        <div className="filter-field"><label htmlFor="end-date">To date</label><input id="end-date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></div>
        <div className="filter-field"><label htmlFor="team-search">Team</label><input id="team-search" value={team} onChange={(event) => setTeam(event.target.value)} maxLength={100} placeholder="Search team" /></div>
        <div className="filter-field"><label htmlFor="match-status">Status</label><select id="match-status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="scheduled">Scheduled</option><option value="live">Live</option><option value="finished">Finished</option><option value="postponed">Postponed</option><option value="abandoned">Abandoned</option><option value="cancelled">Cancelled</option></select></div>
        <button type="submit" disabled={loading}>Apply filters</button>
      </form>
      {error ? <p className="inline-error" role="alert">{error}</p> : null}
      <section aria-live="polite" aria-busy={loading}>
        {loading ? <p className="empty-state">Loading fixtures…</p> : null}
        {!loading && !error && data?.items.length === 0 ? <div className="empty-state"><h2>No fixtures found</h2><p>Import historical CSV results or configure a provider sync before expecting fixtures here.</p></div> : null}
        {!loading && data && data.items.length > 0 ? <>
          <p className="result-count">{data.total} fixture{data.total === 1 ? "" : "s"} · Page {data.page}</p>
          <div className="fixture-list">
            {data.items.map((fixture) => <article className="fixture-row" key={fixture.id}>
              <div className="fixture-meta"><span>{fixture.competition}</span><span className="status-pill">{fixture.status}</span></div>
              <h2>{fixture.home_team} <span>vs</span> {fixture.away_team}</h2>
              <p>{fixture.match_date ?? "Match date unavailable"} · {formatKickoff(fixture.kickoff_at)}</p>
              <span className="coming-label">{fixture.prediction_available ? "Prediction stored" : "No prediction stored"}</span>
            </article>)}
          </div>
          <div className="pagination"><button type="button" disabled={page <= 1 || loading} onClick={() => setPage((current) => current - 1)}>Previous</button><span>Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))}</span><button type="button" disabled={page * data.page_size >= data.total || loading} onClick={() => setPage((current) => current + 1)}>Next</button></div>
        </> : null}
      </section>
    </main>
  );
}
