"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import GoogleSignInButton from "@/components/ui/GoogleSignInButton";
import { track } from "@/lib/analytics";

function LoginForm() {
  const { login, loginWithGoogle } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try { await login(email, password); track("login", { method: "password" }); router.push(safeNext); } catch (err) { setError((err as ApiError).message); } finally { setBusy(false); }
  };
  const handleGoogle = async (token: string) => {
    setError("");
    try { await loginWithGoogle(token); track("login", { method: "google" }); router.push(safeNext); } catch (err) { setError((err as ApiError).message); }
  };

  return (
    <form onSubmit={handleSubmit} className="glass rounded-2xl p-6 space-y-4">
      {error && <div className="p-3 rounded-xl bg-rose-500/10 text-rose-600 text-sm border border-rose-500/20" role="alert">{error}</div>}
      <div><label htmlFor="email" className="text-sm font-medium mb-1.5 block">Email</label><input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm" required /></div>
      <div><label htmlFor="password" className="text-sm font-medium mb-1.5 block">Password</label>
        <div className="relative"><input id="password" type={showPw ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm pr-10" required /><button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Toggle password visibility">{showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div>
      </div>
      <button type="submit" disabled={busy} className="w-full py-2.5 rounded-xl gradient-primary text-white font-medium hover:shadow-lg hover:shadow-indigo-500/25 transition-all disabled:opacity-50">{busy ? "Signing in…" : "Sign in"}</button>
      <GoogleSignInButton onCredential={handleGoogle} />
      <p className="text-center text-sm text-muted-foreground">Don&apos;t have an account? <Link href={`/signup?next=${encodeURIComponent(safeNext)}`} className="text-indigo-500 hover:underline">Sign up</Link></p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl gradient-primary flex items-center justify-center mx-auto mb-4"><Sparkles className="w-7 h-7 text-white" /></div>
          <h1 className="text-2xl font-bold mb-2">Welcome back</h1>
          <p className="text-muted-foreground text-sm">Sign in to manage alerts, saved products and BuyWise Pro.</p>
        </div>
        <Suspense fallback={null}><LoginForm /></Suspense>
      </div>
    </div>
  );
}
