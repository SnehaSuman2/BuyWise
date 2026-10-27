import { API_BASE, tokenStore } from "./api";
import type { TokenResponse } from "./types";

export type SocialProvider = "yahoo" | "microsoft";
const KEY = "buywise:oauth";
export function safeReturnPath(path: string | null): string {
  if (!path?.startsWith("/") || path.startsWith("//") || /[\\\u0000-\u0020]/.test(path)) return "/dashboard";
  return path.startsWith("/auth/") ? "/dashboard" : path;
}
async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v1/auth/oauth/${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), signal: AbortSignal.timeout(45000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Sign-in could not be completed. Please try again.");
  return data as T;
}
export async function startSocialLogin(provider: SocialProvider, next: string) {
  const verifier = Array.from(crypto.getRandomValues(new Uint8Array(32)), b => b.toString(16).padStart(2, "0")).join("");
  const result = await post<{ url: string; state: string }>(`${provider}/start`, { verifier });
  sessionStorage.setItem(KEY, JSON.stringify({ provider, verifier, state: result.state, next: safeReturnPath(next) }));
  window.location.assign(result.url);
}
// One shared promise avoids double-consuming state under React Strict Mode.
let completion: Promise<{ next: string; provider: SocialProvider }> | null = null;
export function completeSocialLogin() {
  if (completion) return completion;
  completion = (async () => {
    const params = new URLSearchParams(window.location.search);
    // Remove authorization codes from history before any navigation or analytics.
    window.history.replaceState({}, "", "/auth/callback");
    const raw = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    if (params.has("error")) throw new Error("Sign-in was cancelled or declined. You can try again or use email.");
    if (!raw) throw new Error("This sign-in has expired. Please start again in this browser.");
    const saved = JSON.parse(raw);
    if (!["yahoo", "microsoft"].includes(saved.provider) || saved.state !== params.get("state") || !params.get("code")) throw new Error("We couldn’t verify this sign-in. Please start again.");
    const tokens = await post<TokenResponse>(`${saved.provider}/complete`, { code: params.get("code"), state: saved.state, verifier: saved.verifier });
    tokenStore.set(tokens);
    return { next: safeReturnPath(saved.next), provider: saved.provider as SocialProvider };
  })();
  return completion;
}
