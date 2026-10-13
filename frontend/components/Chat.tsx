"use client";
import { useEffect, useRef, useState } from "react";
import { api, ChatResp } from "@/lib/api";

type Msg = { role: "user" | "assistant"; text: string; meta?: ChatResp };
const EXAMPLES = ["Analyze Arsenal vs Chelsea.", "Upcoming PL matches with a high chance of over 1.5 goals.", "How well has the model performed historically?"];

export default function Chat({ provider, onError }: { provider: string; onError: (m: string) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [cid, setCid] = useState<number | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, busy]);

  async function send(t = text) {
    const message = t.trim();
    if (!message || busy) return;
    setText("");
    setMsgs((m) => [...m, { role: "user", text: message }]);
    setBusy(true);
    onError("");
    try {
      const r = await api<ChatResp>("/api/chat", { method: "POST", body: JSON.stringify({ message, conversation_id: cid }) });
      setCid(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", text: r.reply, meta: r }]);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto px-3 py-4">
        {msgs.length === 0 && (
          <div className="space-y-2 text-sm text-neutral-400">
            <p>Ask about a fixture. Every probability comes from the statistical engine using <b className="text-neutral-200">{provider}</b> data.</p>
            {EXAMPLES.map((e) => (
              <button key={e} onClick={() => send(e)} className="block w-full rounded-lg border border-neutral-800 px-3 py-2 text-left hover:bg-neutral-900">
                {e}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[92%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm leading-relaxed ${m.role === "user" ? "bg-emerald-700 text-white" : "bg-neutral-900 text-neutral-100"}`}>
              {m.text}
              {m.meta && m.meta.tools_used.length > 0 && (
                <div className="mt-2 border-t border-neutral-800 pt-1 text-[11px] text-neutral-500">
                  Engine calls: {m.meta.tools_used.map((t) => `${t.tool}${t.ok ? "" : " ✗"}`).join(" → ")}
                </div>
              )}
              {m.meta && m.meta.unverified_figures.length > 0 && (
                <div className="mt-1 text-[11px] text-amber-400">Unverified figures: {m.meta.unverified_figures.join(", ")}</div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="text-sm text-neutral-400" role="status">Calculating…</div>}
        <div ref={end} />
      </div>
      <div className="flex gap-2 border-t border-neutral-800 p-3">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          maxLength={2000}
          placeholder="Analyze Arsenal vs Chelsea"
          className="min-w-0 flex-1 rounded-xl border border-neutral-700 bg-neutral-900 px-3 py-2.5 text-base outline-none focus:border-emerald-600"
          aria-label="Message"
        />
        <button onClick={() => send()} disabled={busy || !text.trim()} className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-medium disabled:opacity-40">
          Send
        </button>
      </div>
    </div>
  );
}
