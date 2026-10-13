"use client";
import { useCallback, useEffect, useState } from "react";
import Chat from "@/components/Chat";
import History from "@/components/History";
import ProviderSelect from "@/components/ProviderSelect";
import Settings from "@/components/Settings";
import { api, ProvidersResp } from "@/lib/api";

export default function Home() {
  const [tab, setTab] = useState<"chat" | "history">("chat");
  const [showSettings, setShowSettings] = useState(false);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const [provider, setProvider] = useState("");
  const onError = useCallback((m: string) => setError(m), []);
  useEffect(() => { api<ProvidersResp>("/api/providers").then((r) => setProvider(r.active)).catch(() => {}); }, [tick]);

  return (
    <main className="mx-auto flex h-[100dvh] max-w-2xl flex-col">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 px-3 py-2">
        <h1 className="text-base font-semibold">footy-prediq</h1>
        <div className="flex items-center gap-2">
          <ProviderSelect onError={onError} refreshKey={tick} />
          <button onClick={() => setShowSettings((s) => !s)} className="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-sm" aria-expanded={showSettings}>
            Settings
          </button>
        </div>
      </header>
      {showSettings && <Settings onError={onError} onChanged={() => setTick((t) => t + 1)} />}
      {error && <div role="alert" className="border-b border-red-900 bg-red-950 px-3 py-2 text-sm text-red-200">{error}</div>}
      <nav className="flex border-b border-neutral-800 text-sm">
        {(["chat", "history"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`flex-1 py-2 capitalize ${tab === t ? "border-b-2 border-emerald-500 text-white" : "text-neutral-400"}`}>{t}</button>
        ))}
      </nav>
      {tab === "chat" ? <Chat provider={provider} onError={onError} /> : <History onError={onError} />}
    </main>
  );
}
