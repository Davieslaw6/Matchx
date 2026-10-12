"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

type ApiError = { detail?: { message?: string } | string };

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const result = (await response.json()) as ApiError;
      if (!response.ok) {
        const message = typeof result.detail === "object" ? result.detail?.message : result.detail;
        setError(message || "Sign-in failed. Check the password and try again.");
        return;
      }
      setPassword("");
      router.replace("/");
      router.refresh();
    } catch {
      setError("The API could not be reached. Check that the backend is running.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-title">
        <p className="eyebrow">PRIVATE FOOTBALL INTELLIGENCE</p>
        <h1 id="login-title">MATCH X</h1>
        <h2>Owner sign in</h2>
        <p>Use the password configured with the backend owner CLI. There is no public registration.</p>
        <form onSubmit={submit}>
          <label htmlFor="owner-password">Owner password</label>
          <input
            id="owner-password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={1}
            maxLength={1024}
            required
          />
          {error ? <p role="alert" className="auth-error">{error}</p> : null}
          <button type="submit" disabled={busy || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="auth-note">Statistical estimates only. No automatic wager placement or guaranteed outcomes.</p>
      </section>
    </main>
  );
}
