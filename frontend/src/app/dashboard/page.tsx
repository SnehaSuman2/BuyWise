"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LayoutDashboard, Bookmark, Bell, TrendingDown, Search, Crown, CreditCard, Mail, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPrice, formatRelativeTime, formatDate } from "@/lib/utils";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { Dashboard } from "@/lib/types";

function Section({ icon: Icon, title, children, action }: { icon: React.ElementType; title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="glass rounded-2xl p-5">
      <div className="flex items-center justify-between mb-3"><h2 className="font-semibold flex items-center gap-2"><Icon className="w-4 h-4 text-indigo-500" />{title}</h2>{action}</div>
      {children}
    </section>
  );
}

export default function DashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.dashboard().then(setData).catch((e: ApiError) => setError(e.message));
  useEffect(() => { if (loading) return; if (!user) { router.replace("/login?next=/dashboard"); return; } load(); }, [user, loading, router]);

  const unsave = async (productId: string) => { try { await api.unsaveProduct(productId); load(); } catch (e) { setError((e as ApiError).message); } };

  if (loading || (!user && !error)) return <div className="max-w-6xl mx-auto px-4 py-8"><Spinner /></div>;
  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div><h1 className="text-2xl font-bold flex items-center gap-2"><LayoutDashboard className="w-6 h-6 text-indigo-500" /> Dashboard</h1><p className="text-sm text-muted-foreground mt-1">Hi {data?.user.display_name || user?.username}. Here&apos;s what BuyWise is tracking for you.</p></div>
        <Link href="/account" className="px-4 py-2 rounded-xl glass text-sm font-medium hover:bg-muted/50">Account settings</Link>
      </div>
      {error && <ErrorBox message={error} className="mb-4" />}
      {!data && !error && <Spinner label="Loading your dashboard…" />}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 space-y-4">
            <Section icon={TrendingDown} title="Price drops">
              {data.price_drops.length ? <ul className="space-y-2 text-sm">{data.price_drops.map((d) => <li key={d.alert_id} className="flex justify-between gap-3"><Link href={`/product/${d.product_id}`} className="hover:text-indigo-500 truncate">{d.product_name}</Link><span className="text-emerald-500 font-medium whitespace-nowrap">{formatPrice(d.current_lowest_price)}{d.triggered_at ? ` · ${formatRelativeTime(d.triggered_at)}` : ""}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">No triggered alerts yet.</p>}
            </Section>
            <Section icon={Bookmark} title={`Saved products (${data.saved_products.length}/${data.subscription.limits.saved_products})`}>
              {data.saved_products.length ? (
                <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">{data.saved_products.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 p-2 rounded-xl bg-muted/30">
                                        <img src={s.image || "https://placehold.co/64x64/1a1a2e/e0e0e0?text=?"} alt="" className="w-12 h-12 rounded-lg object-cover" />
                    <div className="flex-1 min-w-0"><Link href={`/product/${s.product_id}`} className="text-sm font-medium truncate block hover:text-indigo-500">{s.name}</Link><div className="text-xs text-muted-foreground">{s.lowest_price ? `from ${formatPrice(s.lowest_price)}` : "no price yet"}{s.note ? ` · ${s.note}` : ""}</div></div>
                    <button onClick={() => unsave(s.product_id)} className="p-1.5 rounded-lg hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500" aria-label="Remove"><Trash2 className="w-4 h-4" /></button>
                  </li>))}</ul>
              ) : <p className="text-sm text-muted-foreground">Save products from any product page to keep an eye on them.</p>}
            </Section>
            <Section icon={Bell} title={`Price alerts (${data.subscription.usage.alerts}/${data.subscription.limits.alerts})`} action={<Link href="/alerts" className="text-xs text-indigo-500 hover:underline">Manage</Link>}>
              {data.alerts.length ? <ul className="space-y-1 text-sm">{data.alerts.slice(0, 6).map((a) => <li key={a.id} className="flex justify-between gap-3"><Link href={`/product/${a.product_id}`} className="truncate hover:text-indigo-500">{a.product_name}</Link><span className="text-muted-foreground whitespace-nowrap">{a.alert_type === "target_price" ? `≤ ${formatPrice(a.target_price)}` : `−${a.drop_percent}%`} · {a.is_triggered ? "met" : a.is_active ? "watching" : "paused"}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">No alerts yet.</p>}
            </Section>
            <Section icon={Search} title="Recent searches">
              {data.recent_searches.length ? <ul className="flex flex-wrap gap-2">{data.recent_searches.map((s) => s.query ? <Link key={s.id} href={`/search?q=${encodeURIComponent(s.query)}`} className="px-3 py-1 rounded-full text-xs glass hover:bg-muted/50 max-w-[240px] truncate">{s.query}</Link> : null)}</ul> : <p className="text-sm text-muted-foreground">No searches yet.</p>}
            </Section>
          </div>
          <div className="space-y-4">
            <Section icon={Crown} title="Subscription" action={<Link href="/pricing" className="text-xs text-indigo-500 hover:underline">{data.subscription.is_pro ? "Manage" : "Upgrade"}</Link>}>
              <div className="text-sm"><span className={`font-semibold ${data.subscription.is_pro ? "text-amber-500" : ""}`}>{data.subscription.is_pro ? "BuyWise Pro" : "Free plan"}</span>{data.subscription.current_period_end && <div className="text-xs text-muted-foreground">{data.subscription.cancel_at_period_end ? "Ends" : "Renews"} {formatDate(data.subscription.current_period_end)}</div>}
                <ul className="text-xs text-muted-foreground mt-2 space-y-0.5"><li>Alerts: {data.subscription.usage.alerts}/{data.subscription.limits.alerts}</li><li>Saved: {data.subscription.usage.saved_products}/{data.subscription.limits.saved_products}</li><li>History: {data.subscription.limits.history_days} days</li></ul>
              </div>
            </Section>
            <Section icon={CreditCard} title="Payments">
              {data.payments.length ? <ul className="space-y-1 text-xs">{data.payments.map((p) => <li key={p.id} className="flex justify-between"><span>{p.plan.replace("_", " ")} · {formatPrice(p.amount / 100)}</span><span className={p.status === "paid" ? "text-emerald-500" : p.status === "failed" ? "text-rose-500" : "text-muted-foreground"}>{p.status}{p.paid_at ? ` · ${formatDate(p.paid_at)}` : ""}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">No payments.</p>}
            </Section>
            <Section icon={Mail} title="Notifications">
              {data.notifications.length ? <ul className="space-y-1 text-xs">{data.notifications.map((n) => <li key={n.id} className="flex justify-between gap-2"><span className="truncate">{n.subject}</span><span className="text-muted-foreground whitespace-nowrap">{n.status} · {formatRelativeTime(n.created_at)}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">Nothing sent yet.</p>}
            </Section>
          </div>
        </div>
      )}
    </div>
  );
}
