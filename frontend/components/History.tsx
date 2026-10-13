"use client";
import { useEffect, useState } from "react";
import { api, HistoryRow } from "@/lib/api";

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export default function History({ onError }: { onError: (m: string) => void }) {
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  useEffect(() => {
    api<HistoryRow[]>("/api/predictions").then(setRows).catch((e) => onError(e.message));
  }, [onError]);
  if (!rows) return <p className="p-4 text-sm text-neutral-400">Loading…</p>;
  if (!rows.length) return <p className="p-4 text-sm text-neutral-400">No stored predictions yet.</p>;
  const ev = rows.filter((r) => r.evaluation);
  return (
    <div className="space-y-3 overflow-y-auto p-3">
      <p className="text-xs text-neutral-500">
        {rows.length} stored · {ev.length} evaluated
        {ev.length > 0 && ` · mean log loss ${(ev.reduce((a, r) => a + r.evaluation!.log_loss, 0) / ev.length).toFixed(3)}`}
        {ev.length < 30 && " · too few evaluated results to judge accuracy"}
      </p>
      {rows.map((r) => (
        <div key={r.prediction_id} className="rounded-xl border border-neutral-800 bg-neutral-900 p-3 text-sm">
          <div className="font-medium">{r.home_team} vs {r.away_team}</div>
          <div className="mt-2 flex h-2 overflow-hidden rounded bg-neutral-800" aria-hidden>
            <div className="bg-emerald-500" style={{ width: pct(r.result.home) }} />
            <div className="bg-neutral-400" style={{ width: pct(r.result.draw) }} />
            <div className="bg-sky-500" style={{ width: pct(r.result.away) }} />
          </div>
          <div className="mt-1 flex justify-between text-xs text-neutral-300">
            <span>H {pct(r.result.home)}</span><span>D {pct(r.result.draw)}</span><span>A {pct(r.result.away)}</span>
          </div>
          <div className="mt-1 text-[11px] text-neutral-500">
            {r.provider} · {r.model_version} · {new Date(r.created_at).toLocaleString()}
            {r.evaluation && ` · actual ${r.evaluation.score} (log loss ${r.evaluation.log_loss.toFixed(3)})`}
          </div>
        </div>
      ))}
    </div>
  );
}
