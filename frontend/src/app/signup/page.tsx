"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import GoogleSignInButton from "@/components/ui/GoogleSignInButton";

function SignupForm() {
  const { register, loginWithGoogle } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
  const [form, setForm] = useState({ email: "", username: "", password: "", confirm: "" });
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const field = "w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== form.confirm) { setError("Passwords do not match"); return; }
    setBusy(true); setError("");
    try { await register({ email: form.email, username: form.username, password: form.password }); router.push(safeNext); } catch (err) { setError((err as ApiError).message); } finally { setBusy(false); }
  };
  const handleGoogle = async (token: string) => { try { await loginWithGoogle(token); router.push(safeNext); } catch (err) { setError((err as ApiError).message); } };

  return (
    <form onSubmit={handleSubmit} className="glass rounded-2xl p-6 space-y-4">
      {error && <div className="p-3 rounded-xl bg-rose-500/10 text-rose-600 text-sm border border-rose-500/20" role="alert">{error}</div>}
      <div><label htmlFor="email" className="text-sm font-medium mb-1.5 block">Email</label><input id="email" type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className={field} required /></div>
      <div><label htmlFor="username" className="text-sm font-medium mb-1.5 block">Username</label><input id="username" type="text" autoComplete="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} pattern="[A-Za-z0-9_.\-]{3,40}" title="3-40 letters, numbers, dots, dashes or underscores" className={field} required /></div>
      <div><label htmlFor="password" className="text-sm font-medium mb-1.5 block">Password</label>
        <div className="relative"><input id="password" type={showPw ? "text" : "password"} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="At least 8 characters with letters and numbers" className={`${field} pr-10`} required minLength={8} /><button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-label="Toggle password visibility">{showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button></div>
      </div>
      <div><label htmlFor="confirm" className="text-sm font-medium mb-1.5 block">Confirm password</label><input id="confirm" type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} className={field} required /></div>
      <button type="submit" disabled={busy} className="w-full py-2.5 rounded-xl gradient-primary text-white font-medium hover:shadow-lg hover:shadow-indigo-500/25 transition-all disabled:opacity-50">{busy ? "Creating…" : "Create account"}</button>
      <GoogleSignInButton onCredential={handleGoogle} />
      <p className="text-xs text-muted-foreground text-center">By signing up you agree to our <Link href="/terms" className="underline">Terms</Link> and <Link href="/privacy" className="underline">Privacy Policy</Link>.</p>
      <p className="text-center text-sm text-muted-foreground">Already have an account? <Link href={`/login?next=${encodeURIComponent(safeNext)}`} className="text-indigo-500 hover:underline">Sign in</Link></p>
    </form>
  );
}

export default function SignupPage() {
  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl gradient-primary flex items-center justify-center mx-auto mb-4"><Sparkles className="w-7 h-7 text-white" /></div>
          <h1 className="text-2xl font-bold mb-2">Create an account</h1>
          <p className="text-muted-foreground text-sm">Track prices, save products and get alerts.</p>
        </div>
        <Suspense fallback={null}><SignupForm /></Suspense>
      </div>
    </div>
  );
}
