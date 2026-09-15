"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Bookmark, BookmarkCheck, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPrice } from "@/lib/utils";

export default function ProductActions({ productId, currentPrice }: { productId: string; currentPrice?: number | null }) {
  const { user } = useAuth();
  const router = useRouter();
  const [saved, setSaved] = useState(false);
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<"target_price" | "percent_drop">("target_price");
  const [target, setTarget] = useState(currentPrice ? Math.round(currentPrice * 0.9) : 0);
  const [percent, setPercent] = useState(10);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!user) return;
    api.savedProducts().then((list) => setSaved(list.some((s) => s.product_id === productId))).catch(() => undefined);
  }, [user, productId]);

  const requireLogin = () => { router.push(`/login?next=/product/${productId}`); };

  const toggleSave = async () => {
    if (!user) return requireLogin();
    setBusy(true);
    try {
      if (saved) { await api.unsaveProduct(productId); setSaved(false); }
      else { await api.saveProduct(productId); setSaved(true); }
    } catch (e) { setMsg({ ok: false, text: (e as ApiError).message }); } finally { setBusy(false); }
  };

  const createAlert = async () => {
    if (!user) return requireLogin();
    setBusy(true); setMsg(null);
    try {
      await api.createAlert(type === "target_price" ? { product_id: productId, alert_type: "target_price", target_price: target } : { product_id: productId, alert_type: "percent_drop", drop_percent: percent });
      setMsg({ ok: true, text: "Alert created. We'll email you when the price qualifies." });
      setOpen(false);
    } catch (e) { setMsg({ ok: false, text: (e as ApiError).message }); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-wrap gap-2 items-center">
      <button onClick={() => (user ? setOpen(true) : requireLogin())} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium hover:shadow-lg transition-all"><Bell className="w-4 h-4" /> Track price</button>
      <button onClick={toggleSave} disabled={busy} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl glass text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50">{saved ? <BookmarkCheck className="w-4 h-4 text-indigo-500" /> : <Bookmark className="w-4 h-4" />} {saved ? "Saved" : "Save"}</button>
      {msg && <span className={`text-xs ${msg.ok ? "text-emerald-500" : "text-rose-500"}`}>{msg.text}</span>}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" role="dialog" aria-modal="true">
          <div className="glass-strong rounded-2xl p-6 w-full max-w-md animate-slide-up">
            <div className="flex items-center justify-between mb-4"><h3 className="font-semibold text-lg">Create price alert</h3><button onClick={() => setOpen(false)} aria-label="Close" className="p-1 rounded-lg hover:bg-muted"><X className="w-4 h-4" /></button></div>
            {currentPrice ? <p className="text-sm text-muted-foreground mb-4">Current lowest estimated final price: <strong>{formatPrice(currentPrice)}</strong></p> : null}
            <div className="flex gap-2 mb-4">
              <button onClick={() => setType("target_price")} className={`flex-1 px-3 py-2 rounded-xl text-sm border ${type === "target_price" ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40"}`}>Reaches a price</button>
              <button onClick={() => setType("percent_drop")} className={`flex-1 px-3 py-2 rounded-xl text-sm border ${type === "percent_drop" ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40"}`}>Drops by %</button>
            </div>
            {type === "target_price" ? (
              <label className="block text-sm mb-4">Alert me when the price is at or below (₹)<input type="number" min={1} value={target} onChange={(e) => setTarget(Number(e.target.value))} className="mt-1 w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30" /></label>
            ) : (
              <label className="block text-sm mb-4">Alert me when the price drops by (%)<input type="number" min={1} max={90} value={percent} onChange={(e) => setPercent(Number(e.target.value))} className="mt-1 w-full px-4 py-2.5 rounded-xl bg-muted/50 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30" /></label>
            )}
            {msg && !msg.ok && <p className="text-sm text-rose-500 mb-3">{msg.text}</p>}
            <button onClick={createAlert} disabled={busy} className="w-full py-2.5 rounded-xl gradient-primary text-white font-medium disabled:opacity-50">{busy ? "Creating…" : "Create alert"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
