"use client";
import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { startSocialLogin, type SocialProvider } from "@/lib/oauth";
import { track } from "@/lib/analytics";
import GoogleSignInButton from "./GoogleSignInButton";

export default function SocialSignInButtons({ next, onGoogle }: { next: string; onGoogle: (credential: string) => void }) {
  const [providers, setProviders] = useState<{ yahoo?: boolean; microsoft?: boolean; google_client_id?: string } | null>(null);
  const [busy, setBusy] = useState<SocialProvider | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/v1/auth/providers`, { signal: AbortSignal.timeout(12000) })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(data => { if (active) setProviders(data); })
      .catch(() => { if (active) { setProviders({}); setError("Other sign-in methods aren’t available right now. You can still use email."); } });
    return () => { active = false; };
  }, []);
  async function begin(provider: SocialProvider) {
    setBusy(provider); setError(""); track("login_started", { method: provider });
    try { await startSocialLogin(provider, next); }
    catch (e) { setError(e instanceof Error ? e.message : "Please try signing in again."); setBusy(null); }
  }
  return <div className="space-y-3">
    <GoogleSignInButton onCredential={onGoogle} configuredClientId={providers?.google_client_id} />
    <div className="grid grid-cols-2 gap-3">{(["yahoo", "microsoft"] as const).map(provider => <button key={provider} type="button" disabled={!providers?.[provider] || busy !== null} onClick={() => void begin(provider)} aria-describedby="social-status" className="min-h-12 flex items-center justify-center gap-2 rounded-xl border border-border px-3 py-3 text-sm font-medium hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed">
      {busy === provider ? <LoaderCircle size={18} className="animate-spin" /> : provider === "yahoo" ? <span className="text-violet-600 font-black text-lg" aria-hidden="true">y!</span> : <span aria-hidden="true" className="grid grid-cols-2 gap-0.5 w-4 h-4"><i className="bg-orange-500" /><i className="bg-green-500" /><i className="bg-blue-500" /><i className="bg-yellow-500" /></span>}
      {provider === "yahoo" ? "Yahoo" : "Microsoft"}
    </button>)}</div>
    <p id="social-status" className="text-xs text-muted-foreground text-center">{!providers ? "Checking sign-in options…" : !providers.yahoo || !providers.microsoft ? "Dimmed options are currently unavailable. Use email or an available provider." : "Continue with an account you already use."}</p>
    {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
    <div className="flex items-center gap-3 py-2 text-xs text-muted-foreground"><span className="h-px bg-border flex-1" />or continue with email<span className="h-px bg-border flex-1" /></div>
  </div>;
}
