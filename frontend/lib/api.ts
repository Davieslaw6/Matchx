const KEY = "footy_token";

export const getToken = (): string => (typeof window === "undefined" ? "" : sessionStorage.getItem(KEY) || "");
export const setToken = (t: string) => (t ? sessionStorage.setItem(KEY, t) : sessionStorage.removeItem(KEY));

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...((init.headers as Record<string, string>) || {}) };
  const t = getToken();
  if (t) headers.Authorization = `Bearer ${t}`;
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers });
  } catch {
    throw new Error("Cannot reach the backend. Is it running?");
  }
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try {
      const d = (await r.json()).detail;
      if (typeof d === "string") msg = d;
      else if (Array.isArray(d)) msg = d.map((x: { msg?: string }) => x.msg).join("; ");
    } catch {}
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export type ProviderInfo = { name: string; configured: boolean; active: boolean };
export type ProvidersResp = { active: string; providers: ProviderInfo[] };
export type ToolTrace = { tool: string; args: Record<string, unknown>; ok: boolean };
export type ChatResp = { conversation_id: number; reply: string; tools_used: ToolTrace[]; unverified_figures: string[]; provider: string };
export type HistoryRow = {
  prediction_id: number; fixture_id: number; model_version: string; provider: string | null; created_at: string;
  home_team: string; away_team: string; result: { home: number; draw: number; away: number };
  evaluation: { score: string; log_loss: number; brier: number } | null;
};
export const LEAGUES = ["PL", "PD", "SA", "BL1", "FL1"];
