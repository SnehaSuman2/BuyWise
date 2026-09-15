"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, Trash2, Target, Pause, Play, CheckCircle2, Search } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPrice, formatRelativeTime } from "@/lib/utils";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { PriceAlert } from "@/lib/types";

export default function AlertsPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [alerts, setAlerts] = useState<PriceAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace("/login?next=/alerts"); return; }
    api.alerts().then(setAlerts).catch((e: ApiError) => setError(e.message));
  }, [user, authLoading, router]);

  const update = (a: PriceAlert) => setAlerts((list) => (list || []).map((x) => (x.id === a.id ? a : x)));
  const remove = async (id: string) => { try { await api.deleteAlert(id); setAlerts((l) => (l || []).filter((x) => x.id !== id)); } catch (e) { setError((e as ApiError).message); } };
  const toggle = async (a: PriceAlert) => { try { update(a.is_active ? await api.pauseAlert(a.id) : await api.resumeAlert(a.id)); } catch (e) { setError((e as ApiError).message); } };

  if (authLoading || (!user && !error)) return <div className="max-w-4xl mx-auto px-4 py-8"><Spinner /></div>;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Bell className="w-6 h-6 text-indigo-500" /> Price alerts</h1>
          <p className="text-muted-foreground text-sm mt-1">We check tracked products in the background and email you when your target is met.</p>
        </div>
        <Link href="/" className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium flex items-center gap-2 hover:shadow-lg transition-all"><Search className="w-4 h-4" /> Find a product to track</Link>
      </div>
      {error && <ErrorBox message={error} className="mb-4" />}
      {!alerts && !error && <Spinner label="Loading alerts…" />}
      {alerts && alerts.length === 0 && (
        <div className="text-center py-20 glass rounded-2xl"><Bell className="w-12 h-12 text-muted-foreground mx-auto mb-4" /><h3 className="text-lg font-semibold mb-2">No price alerts yet</h3><p className="text-muted-foreground text-sm">Open any product and click &quot;Track price&quot; to set a target price or a percentage drop.</p></div>
      )}
      {alerts && alerts.length > 0 && (
        <div className="space-y-4">
          {alerts.map((alert, i) => {
            const goal = alert.alert_type === "target_price" ? alert.target_price : alert.baseline_price && alert.drop_percent ? alert.baseline_price * (1 - alert.drop_percent / 100) : null;
            const gap = goal && alert.current_lowest_price ? alert.current_lowest_price - goal : null;
            const progress = goal && alert.current_lowest_price && alert.baseline_price && alert.baseline_price > goal ? Math.min(100, Math.max(0, ((alert.baseline_price - alert.current_lowest_price) / (alert.baseline_price - goal)) * 100)) : alert.is_triggered ? 100 : 0;
            return (
              <div key={alert.id} className={`glass rounded-2xl p-5 animate-slide-up ${!alert.is_active ? "opacity-60" : ""}`} style={{ animationDelay: `${i * 0.06}s`, opacity: 0, animationFillMode: "forwards" }}>
                <div className="flex items-start gap-4">
                                    <img src={alert.product_image || "https://placehold.co/80x80/1a1a2e/e0e0e0?text=?"} alt="" className="w-16 h-16 rounded-xl object-cover" />
                  <div className="flex-1 min-w-0">
                    <Link href={`/product/${alert.product_id}`} className="font-semibold text-sm mb-1 block truncate hover:text-indigo-500">{alert.product_name || "Product"}</Link>
                    <div className="flex items-center gap-4 mb-3 flex-wrap text-sm">
                      <div><div className="text-xs text-muted-foreground">{alert.alert_type === "target_price" ? "Target" : `Drop ${alert.drop_percent}% from ${formatPrice(alert.baseline_price)}`}</div><div className="font-bold text-emerald-500 flex items-center gap-1"><Target className="w-3 h-3" />{goal ? formatPrice(goal) : "—"}</div></div>
                      <div><div className="text-xs text-muted-foreground">Current lowest</div><div className="font-bold">{alert.current_lowest_price ? formatPrice(alert.current_lowest_price) : "—"}</div></div>
                      {alert.is_triggered ? <div className="text-emerald-500 font-medium flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Target met{alert.triggered_at ? ` ${formatRelativeTime(alert.triggered_at)}` : ""}</div> : gap && gap > 0 ? <div><div className="text-xs text-muted-foreground">Gap</div><div className="font-medium text-amber-500">{formatPrice(gap)} away</div></div> : null}
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 rounded-full transition-all duration-1000" style={{ width: `${progress}%` }} /></div>
                    <div className="text-[11px] text-muted-foreground mt-2">{alert.is_active ? "Active" : "Paused"} · checked {alert.last_checked_at ? formatRelativeTime(alert.last_checked_at) : "not yet"} · via {alert.notification_method}</div>
                  </div>
                  <div className="flex flex-col gap-1">
                    <button onClick={() => toggle(alert)} className="p-2 rounded-lg hover:bg-muted text-muted-foreground" aria-label={alert.is_active ? "Pause alert" : "Resume alert"}>{alert.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}</button>
                    <button onClick={() => remove(alert.id)} className="p-2 rounded-lg hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500 transition-colors" aria-label="Delete alert"><Trash2 className="w-4 h-4" /></button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
