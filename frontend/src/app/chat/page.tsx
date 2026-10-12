"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type ChatMessage = { id?: string; role: "user" | "assistant"; content: string; metadata?: { sources?: Source[]; tool_calls?: { name: string; status: string }[] } };
type Source = { type: string; id: string };
type Conversation = { id: string; title: string; updated_at: string };
type ApiError = { message?: string; detail?: { message?: string } };
type ChatResponse = { conversation_id: string; answer: string; model: string; tool_calls: { name: string; status: string }[]; sources: Source[] };

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadConversations = useCallback(async () => {
    const response = await fetch("/api/v1/ai/conversations", { credentials: "same-origin" });
    if (response.status === 401) {
      router.replace("/login");
      return;
    }
    if (!response.ok) return;
    const data = (await response.json()) as { items: Conversation[] };
    setConversations(data.items);
  }, [router]);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/auth/session", { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (response.status === 401) {
          router.replace("/login");
          return false;
        }
        if (!response.ok) throw new Error("Could not verify owner session.");
        return true;
      })
      .then((authenticated) => {
        if (authenticated && !controller.signal.aborted) void loadConversations();
      })
      .catch((cause: unknown) => {
        if (cause instanceof Error && cause.name !== "AbortError") setError(cause.message);
      });
    return () => controller.abort();
  }, [loadConversations, router]);

  async function openConversation(id: string) {
    setError("");
    const response = await fetch(`/api/v1/ai/conversations/${encodeURIComponent(id)}`, { credentials: "same-origin" });
    if (response.status === 401) {
      router.replace("/login");
      return;
    }
    const data = (await response.json()) as { id: string; messages?: ChatMessage[]; detail?: ApiError["detail"] };
    if (!response.ok) {
      setError(data.detail?.message || "Could not open conversation.");
      return;
    }
    setConversationId(data.id);
    setMessages(data.messages ?? []);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || loading) return;
    setLoading(true);
    setError("");
    const csrfCookie = document.cookie.split("; ").find((item) => item.startsWith("matchx_csrf="));
    const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice("matchx_csrf=".length)) : "";
    if (!csrfToken) {
      setError("Your CSRF token is missing. Sign out and sign in again.");
      setLoading(false);
      return;
    }
    try {
      const response = await fetch("/api/v1/ai/chat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify({ message, ...(conversationId ? { conversation_id: conversationId } : {}) }),
      });
      const body = (await response.json()) as ChatResponse & { detail?: ApiError["detail"]; message?: string };
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error(body.detail?.message || body.message || "AI request failed.");
      setConversationId(body.conversation_id);
      setMessages((current) => [
        ...current,
        { role: "user", content: message },
        { role: "assistant", content: body.answer, metadata: { sources: body.sources, tool_calls: body.tool_calls } },
      ]);
      setDraft("");
      await loadConversations();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AI request failed.");
    } finally {
      setLoading(false);
    }
  }

  function onDraftChange(event: ChangeEvent<HTMLTextAreaElement>) {
    setDraft(event.target.value);
  }

  function newConversation() {
    setConversationId(null);
    setMessages([]);
    setError("");
  }

  return (
    <main className="dashboard chat-layout">
      <header className="page-header">
        <div><p className="eyebrow">MATCH X / ASSISTANT</p><h1>Football analysis chat</h1></div>
        <Link href="/explorer" className="text-link">Match explorer</Link>
      </header>
      <p className="page-intro">Answers are grounded in records stored by MATCH X. Missing data is reported as unavailable; the assistant does not place wagers.</p>
      <div className="chat-shell">
        <aside className="conversation-sidebar">
          <button type="button" className="new-chat-button" onClick={newConversation}>＋ New conversation</button>
          <h2>Recent conversations</h2>
          {conversations.length === 0 ? <p className="sidebar-empty">No saved conversations yet.</p> : conversations.map((item) => <button type="button" className={conversationId === item.id ? "conversation-link selected" : "conversation-link"} key={item.id} onClick={() => void openConversation(item.id)}>{item.title}</button>)}
        </aside>
        <section className="chat-panel" aria-label="Chat conversation">
          <div className="chat-messages" aria-live="polite">
            {messages.length === 0 ? <div className="chat-empty"><h2>Ask about stored football data</h2><p>Examples: “Find upcoming Premier League fixtures”, “Show the stored prediction for this fixture”, or “Summarize this team’s recent results.”</p></div> : messages.map((message, index) => <article className={message.role === "user" ? "chat-message user-message" : "chat-message assistant-message"} key={message.id ?? `${message.role}-${index}`}>
              <span className="message-role">{message.role === "user" ? "You" : "MATCH X assistant"}</span>
              <p>{message.content}</p>
              {message.metadata?.sources?.length ? <div className="source-list"><span>Retrieved sources:</span>{message.metadata.sources.map((source) => source.type === "fixture" ? <Link key={source.id} href={`/analysis/${encodeURIComponent(source.id)}`}>Fixture {source.id.slice(0, 8)}</Link> : <span key={source.id}>{source.type} {source.id.slice(0, 8)}</span>)}</div> : null}
              {message.metadata?.tool_calls?.length ? <details className="tool-details"><summary>Data tools used ({message.metadata.tool_calls.length})</summary><ul>{message.metadata.tool_calls.map((tool, i) => <li key={`${tool.name}-${i}`}>{tool.name} · {tool.status}</li>)}</ul></details> : null}
            </article>)}
            {loading ? <p className="assistant-thinking" role="status">Checking stored data…</p> : null}
          </div>
          {error ? <p className="inline-error chat-error" role="alert">{error}</p> : null}
          <form className="chat-composer" onSubmit={submit}>
            <textarea value={draft} onChange={onDraftChange} rows={3} maxLength={5000} placeholder="Ask about a fixture, team form, result or stored prediction…" aria-label="Message" disabled={loading} />
            <div className="composer-footer"><span>{draft.length}/5000 · Requires backend LLM configuration</span><button type="submit" disabled={loading || !draft.trim()}>{loading ? "Working…" : "Send"}</button></div>
          </form>
        </section>
      </div>
      <p className="responsible-note">AI output can be wrong. Numeric claims are checked against retrieved tool data; if grounding fails, MATCH X falls back to the retrieved records. Model estimates are not guarantees of future performance.</p>
    </main>
  );
}
