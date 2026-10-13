"use client";
import { useState } from "react";
import { api, getToken, LEAGUES, setToken } from "@/lib/api";

type SyncRes = Record<string, { new_fixtures: number; results_recorded: number; notes: string[] }>;
type BtRes = { n_predictions: number; model: { log_loss: number }; baseline_outcome_frequencies: { log_loss: number }; verdict: string };

export default function Settings({ onError, onChanged }: { onError: (m: string) => void; onChanged: () => void }) {
  const [token, setTok] = useState(getToken());
  const [league, setLeague] = useState("ALL");
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState("");
  const targets = league === "ALL" ? LEAGUES : [league];

  async function run(label: string, fn: () => Promise<string>) {
    setBusy(label); onError("");
    try { setLog(await fn()); } catch (e) { onError((e as Error).message); } finally { setBusy(""); }
  }
  const each = async (fn: (c: string) => Promise<string>) => {
    const out: string[] = [];
    for (const c of targets) { try { out.push(await fn(c)); } catch (e) { out.push(`${c}: ${(e as Error).message}`); } }
    return out.join("\n");
  };
  const sync = () => run("sync", async () => {
    const r = await api<SyncRes>("/api/sync", { method: "POST", body: JSON.stringify({ competitions: targets }) });
    return Object.entries(r).map(([k, v]) => `${k}: ${v.new_fixtures} new fixtures, ${v.results_recorded} results${v.notes.length ? " — " + v.notes.join("; ") : ""}`).join("\n");
  });
  const train = () => run("train", () => each(async (c) => { const r = await api<{ n_matches: number }>(`/api/train/${c}`, { method: "POST" }); return `${c}: trained on ${r.n_matches} matches`; }));
  const backtest = () => run("backtest", () => each(async (c) => {
    const r = await api<BtRes>(`/api/backtest/${c}`, { method: "POST" });
    return `${c}: ${r.n_predictions} predictions, log loss ${r.model.log_loss.toFixed(3)} vs baseline ${r.baseline_outcome_frequencies.log_loss.toFixed(3)} — ${r.verdict}`;
  }));
  const wipe = () => {
    if (!confirm("Delete ALL conversation history? This cannot be undone.")) return;
    run("delete", async () => { await api("/api/conversations", { method: "DELETE" }); return "Conversation history deleted."; });
  };
  const btn = "rounded-lg border border-neutral-700 px-3 py-2 text-sm hover:bg-neutral-800 disabled:opacity-40";

  return (
    <div className="space-y-3 border-b border-neutral-800 bg-neutral-900/60 p-3 text-sm">
      <div className="flex gap-2">
        <input type="password" value={token} onChange={(e) => setTok(e.target.value)} placeholder="Access token (if configured)"
          className="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2" aria-label="Access token" />
        <button className={btn} onClick={() => { setToken(token); onChanged(); }}>Save</button>
      </div>
      <p className="text-[11px] text-neutral-500">Kept in this browser tab only (session storage). API keys live in the backend environment.</p>
      <div className="flex flex-wrap items-center gap-2">
        <select value={league} onChange={(e) => setLeague(e.target.value)} className="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-2" aria-label="League">
          <option value="ALL">All leagues</option>{LEAGUES.map((l) => <option key={l}>{l}</option>)}
        </select>
        <button className={btn} disabled={!!busy} onClick={sync}>{busy === "sync" ? "Syncing…" : "Sync data"}</button>
        <button className={btn} disabled={!!busy} onClick={train}>{busy === "train" ? "Training…" : "Train"}</button>
        <button className={btn} disabled={!!busy} onClick={backtest}>{busy === "backtest" ? "Running…" : "Backtest"}</button>
      </div>
      <p className="text-[11px] text-neutral-500">Sync respects provider rate limits and can take a minute or more. Switching provider keeps data separate: sync and train again.</p>
      {log && <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg bg-neutral-950 p-2 text-xs text-neutral-300">{log}</pre>}
      <button className={`${btn} text-red-300`} disabled={!!busy} onClick={wipe}>Delete conversation history</button>
    </div>
  );
}
