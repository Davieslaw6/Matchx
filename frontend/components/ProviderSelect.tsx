"use client";
import { useEffect, useState } from "react";
import { api, ProvidersResp } from "@/lib/api";

export default function ProviderSelect({ onError, refreshKey }: { onError: (m: string) => void; refreshKey: number }) {
  const [data, setData] = useState<ProvidersResp | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<ProvidersResp>("/api/providers").then(setData).catch((e) => onError(e.message));
  }, [refreshKey, onError]);

  async function choose(name: string) {
    setBusy(true);
    try {
      await api("/api/provider", { method: "PUT", body: JSON.stringify({ name }) });
      setData(await api<ProvidersResp>("/api/providers"));
      onError("");
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <span className="text-xs text-neutral-500">Loading providers…</span>;
  return (
    <label className="flex items-center gap-2 text-xs text-neutral-400">
      Data source
      <select
        value={data.active}
        disabled={busy}
        onChange={(e) => choose(e.target.value)}
        className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm text-neutral-100"
        aria-label="Data provider"
      >
        {data.providers.map((p) => (
          <option key={p.name} value={p.name} disabled={!p.configured}>
            {p.name}
            {p.configured ? "" : " (no key)"}
          </option>
        ))}
      </select>
    </label>
  );
}
