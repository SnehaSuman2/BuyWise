"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Crown, Check, CreditCard, AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMeta } from "@/lib/meta";
import { formatPrice, formatDate } from "@/lib/utils";
import type { PlanInfo, SubscriptionStatus } from "@/lib/types";

declare global { interface Window { Razorpay?: new (opts: Record<string, unknown>) => { open: () => void } } }

function loadRazorpay(): Promise<boolean> {
  return new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });
}

export default function PricingPage() {
  const { user, refreshUser } = useAuth();
  const { meta } = useMeta();
  const router = useRouter();
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [sub, setSub] = useState<SubscriptionStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => { api.plans().then(setPlans).catch(() => setPlans([])); }, []);
  useEffect(() => { if (!user) return; api.subscription().then(setSub).catch(() => setSub(null)); }, [user]);
  const currentSub = user ? sub : null;

  const checkout = async (planId: string) => {
    if (!user) { router.push(`/login?next=/pricing`); return; }
    setBusy(planId); setMsg(null);
    try {
      const order = await api.createOrder(planId);
      if (!(await loadRazorpay()) || !window.Razorpay) throw new Error("Could not load Razorpay checkout");
      const rzp = new window.Razorpay({
        key: order.key_id, amount: order.amount, currency: order.currency, name: order.name, description: order.description, order_id: order.order_id, prefill: order.prefill, theme: { color: "#6366f1" },
        handler: async (resp: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
          try {
            const status = await api.verifyPayment(resp);  // server-side verification decides activation
            setSub(status); await refreshUser();
            setMsg({ ok: true, text: "Payment verified. Welcome to BuyWise Pro!" });
          } catch (e) { setMsg({ ok: false, text: `Payment could not be verified: ${(e as ApiError).message}` }); }
        },
        modal: { ondismiss: () => setBusy(null) },
      });
      rzp.open();
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(null); }
  };

  const cancel = async () => { setBusy("cancel"); try { setSub(await api.cancelSubscription()); await refreshUser(); setMsg({ ok: true, text: "Your Pro plan will end at the end of the current period." }); } catch (e) { setMsg({ ok: false, text: (e as ApiError).message }); } finally { setBusy(null); } };

  return (
    <div className="max-w-5xl mx-auto px-4 py-12">
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-amber-500/10 text-amber-600 text-sm font-medium mb-4"><Crown className="w-4 h-4" /> BuyWise Pro</div>
        <h1 className="text-3xl font-bold mb-3">More tracking. Deeper insight. Same honest data.</h1>
        <p className="text-muted-foreground">Pro pays for the data and compute behind BuyWise. It never changes Trust Scores or rankings.</p>
      </div>
      {meta && !meta.payments_enabled && <p className="mb-6 text-sm text-amber-600 flex items-center justify-center gap-2"><AlertTriangle className="w-4 h-4" /> Payments are not configured on this deployment yet (Razorpay keys missing). Plans are shown for reference.</p>}
      {msg && <div className={`mb-6 p-3 rounded-xl text-sm border text-center ${msg.ok ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" : "bg-rose-500/10 text-rose-600 border-rose-500/20"}`}>{msg.text}</div>}
      {currentSub?.is_pro && <div className="mb-6 glass rounded-2xl p-4 text-sm flex flex-wrap items-center justify-between gap-3"><span>You are on <strong>{currentSub.plan.replace("_", " ")}</strong>{currentSub.current_period_end ? ` until ${formatDate(currentSub.current_period_end)}` : ""}{currentSub.cancel_at_period_end ? " (cancellation scheduled)" : ""}.</span>{!currentSub.cancel_at_period_end && <button onClick={cancel} disabled={busy === "cancel"} className="px-3 py-1.5 rounded-lg glass text-xs font-medium hover:bg-muted/50">Cancel renewal</button>}</div>}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {plans.map((p) => {
          const current = currentSub ? (p.id === "free" ? !currentSub.is_pro : currentSub.plan === p.id) : p.id === "free" && !!user;
          return (
            <div key={p.id} className={`glass rounded-2xl p-6 flex flex-col ${p.id === "pro_yearly" ? "ring-2 ring-indigo-500/40" : ""}`}>
              <h2 className="font-semibold text-lg">{p.name}</h2>
              <div className="text-3xl font-bold my-2">{p.price_inr ? formatPrice(p.price_inr) : "₹0"}<span className="text-sm font-normal text-muted-foreground">{p.period_days === 30 ? "/month" : p.period_days === 365 ? "/year" : ""}</span></div>
              <ul className="space-y-1.5 text-sm text-muted-foreground flex-1 mb-4">{p.features.map((f) => <li key={f} className="flex gap-2"><Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />{f}</li>)}</ul>
              {p.id === "free" ? <div className="text-center text-sm text-muted-foreground">{current ? "Current plan" : "Included"}</div> : (
                <button onClick={() => checkout(p.id)} disabled={busy === p.id || current || (meta ? !meta.payments_enabled : false)} className="w-full py-2.5 rounded-xl gradient-primary text-white font-medium flex items-center justify-center gap-2 disabled:opacity-50"><CreditCard className="w-4 h-4" />{current ? "Current plan" : busy === p.id ? "Opening checkout…" : user ? "Pay with Razorpay" : "Sign in to subscribe"}</button>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground text-center mt-8">Payments are processed by Razorpay and verified on our servers before activation. Prices include applicable taxes unless stated otherwise at checkout.</p>
    </div>
  );
}
