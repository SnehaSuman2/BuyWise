"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { User as UserIcon, KeyRound, Bell, AlertTriangle, LogOut } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import Spinner from "@/components/ui/Spinner";

export default function AccountPage() {
  const { user, loading, refreshUser, logout } = useAuth();
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [prefs, setPrefs] = useState<Record<string, boolean>>({ email: true, price_alerts: true, product_updates: false });
  const [pw, setPw] = useState({ current: "", next: "" });
  const [del, setDel] = useState({ confirm: "", password: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [initFor, setInitFor] = useState<string | null>(null);
  if (user && initFor !== user.id) {
    setInitFor(user.id);
    setDisplayName(user.display_name || "");
    setPrefs({ email: true, price_alerts: true, product_updates: false, ...(user.notification_preferences || {}) });
  }
  const field = "w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm";

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login?next=/account");
  }, [user, loading, router]);

  const run = async (fn: () => Promise<unknown>, ok: string) => { setMsg(null); try { await fn(); setMsg({ ok: true, text: ok }); } catch (e) { setMsg({ ok: false, text: (e as ApiError).message }); } };

  if (loading || !user) return <div className="max-w-3xl mx-auto px-4 py-8"><Spinner /></div>;
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><UserIcon className="w-6 h-6 text-indigo-500" /> Account</h1>
      {msg && <div className={`p-3 rounded-xl text-sm border ${msg.ok ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" : "bg-rose-500/10 text-rose-600 border-rose-500/20"}`} role="status">{msg.text}</div>}

      <section className="glass rounded-2xl p-6 space-y-3">
        <h2 className="font-semibold">Profile</h2>
        <div className="text-sm text-muted-foreground">Email: {user.email} · Username: {user.username} · Plan: <span className="capitalize">{user.plan}</span> · Sign-in: {user.auth_provider}</div>
        <label className="block text-sm">Display name<input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={`${field} mt-1`} maxLength={100} /></label>
        <button onClick={() => run(async () => { await api.updateAccount({ display_name: displayName }); await refreshUser(); }, "Profile updated")} className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">Save</button>
      </section>

      <section className="glass rounded-2xl p-6 space-y-3">
        <h2 className="font-semibold flex items-center gap-2"><Bell className="w-4 h-4 text-indigo-500" /> Notification preferences</h2>
        {[["email", "Email notifications (master switch)"], ["price_alerts", "Price alert emails"], ["product_updates", "Product updates from BuyWise"]].map(([k, label]) => (
          <label key={k} className="flex items-center gap-3 text-sm"><input type="checkbox" checked={!!prefs[k]} onChange={(e) => setPrefs({ ...prefs, [k]: e.target.checked })} className="w-4 h-4 accent-indigo-500" />{label}</label>
        ))}
        <button onClick={() => run(async () => { await api.updateAccount({ notification_preferences: prefs }); await refreshUser(); }, "Preferences saved")} className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">Save preferences</button>
      </section>

      <section className="glass rounded-2xl p-6 space-y-3">
        <h2 className="font-semibold flex items-center gap-2"><KeyRound className="w-4 h-4 text-indigo-500" /> {user.auth_provider === "google" ? "Set a password" : "Change password"}</h2>
        {user.auth_provider !== "google" && <label className="block text-sm">Current password<input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} className={`${field} mt-1`} /></label>}
        <label className="block text-sm">New password<input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} className={`${field} mt-1`} minLength={8} /></label>
        <button onClick={() => run(async () => { await api.changePassword({ current_password: pw.current || undefined, new_password: pw.next }); setPw({ current: "", next: "" }); await logout(); router.push("/login"); }, "Password changed — please sign in again")} className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">Update password</button>
        <p className="text-xs text-muted-foreground">Changing your password signs you out of every device.</p>
      </section>

      <section className="glass rounded-2xl p-6 space-y-3">
        <h2 className="font-semibold flex items-center gap-2"><LogOut className="w-4 h-4 text-indigo-500" /> Sessions</h2>
        <button onClick={() => run(async () => { await api.logoutAll(); await logout(); router.push("/login"); }, "Signed out everywhere")} className="px-4 py-2 rounded-xl glass text-sm font-medium hover:bg-muted/50">Sign out of all devices</button>
      </section>

      <section className="glass rounded-2xl p-6 space-y-3 border border-rose-500/20">
        <h2 className="font-semibold flex items-center gap-2 text-rose-500"><AlertTriangle className="w-4 h-4" /> Delete account</h2>
        <p className="text-sm text-muted-foreground">Deletes your profile, saved products and alerts, and anonymises your data. Payment records are kept for accounting as required by law. This cannot be undone.</p>
        <label className="block text-sm">Type DELETE to confirm<input value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} className={`${field} mt-1`} /></label>
        {user.auth_provider !== "google" && <label className="block text-sm">Password<input type="password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} className={`${field} mt-1`} /></label>}
        <button disabled={del.confirm !== "DELETE"} onClick={() => run(async () => { await api.deleteAccount({ confirm: del.confirm, password: del.password || undefined }); await logout(); router.push("/"); }, "Account deleted")} className="px-4 py-2 rounded-xl bg-rose-500 text-white text-sm font-medium disabled:opacity-40">Delete my account</button>
      </section>
    </div>
  );
}
