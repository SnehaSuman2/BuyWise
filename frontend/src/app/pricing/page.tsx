"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Crown, Check, AlertTriangle, QrCode, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useMeta } from "@/lib/meta";
import { track } from "@/lib/analytics";
import { formatPrice, formatDate } from "@/lib/utils";
import type { PlanInfo, SubscriptionStatus } from "@/lib/types";

type RazorpayFailure = { error?: { description?: string; reason?: string; step?: string } };
type RazorpayCheckout = { open: () => void; on: (event: string, handler: (r: RazorpayFailure) => void) => void };
declare global { interface Window { Razorpay?: new (opts: Record<string, unknown>) => RazorpayCheckout } }

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

/** How the period reads under the price. */
function periodLabel(days: number): string {
  if (days === 30) return "for 1 month";
  if (days === 365) return "for 12 months";
  return `for ${Math.round(days / 30)} months`;
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
    if (meta && meta.payments_ready === false) { setMsg({ ok: false, text: "Checkout is unavailable right now: Razorpay is not accepting this site's payment keys." }); return; }
    setBusy(planId); setMsg(null);
    try {
      const order = await api.createOrder(planId);
      if (!(await loadRazorpay()) || !window.Razorpay) throw new Error("Could not load Razorpay checkout");
      track("begin_checkout", { plan: planId, value: order.amount / 100, currency: "INR" });
      const rzp = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: order.name,
        description: order.description,
        order_id: order.order_id,
        prefill: order.prefill,
        theme: { color: "#6366f1" },
        // UPI first: on a computer this opens a QR to scan with any UPI app, and
        // on a phone it hands off to GPay, PhonePe, Paytm and the rest. Cards and
        // netbanking stay available underneath.
        config: {
          display: {
            blocks: {
              upi: { name: "Pay by UPI — scan a QR or use your app", instruments: [{ method: "upi" }] },
            },
            sequence: ["block.upi"],
            preferences: { show_default_blocks: true },
          },
        },
        handler: async (resp: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
          try {
            const status = await api.verifyPayment(resp);  // server-side verification decides activation
            setSub(status); await refreshUser();
            track("purchase", { plan: planId, value: order.amount / 100, currency: "INR" });
            setMsg({ ok: true, text: "Payment verified. Welcome to BuyWise Pro!" });
          } catch (e) { setMsg({ ok: false, text: `Payment could not be verified: ${(e as ApiError).message}` }); }
        },
        modal: { ondismiss: () => setBusy(null) },
      });
      // A payment can fail inside the modal (a declined card, a UPI request that
      // times out) without the handler above ever running. Without this the
      // modal simply closed and the page said nothing at all.
      rzp.on("payment.failed", (r) => {
        const why = r?.error?.description || r?.error?.reason || "the payment did not go through";
        track("payment_failed", { plan: planId, reason: r?.error?.reason });
        setMsg({ ok: false, text: `Payment failed: ${why}. Nothing was charged. You can try again, or use another method.` });
        setBusy(null);
      });
      rzp.open();
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setBusy(null); }
  };

  const cancel = async () => { setBusy("cancel"); try { setSub(await api.cancelSubscription()); await refreshUser(); setMsg({ ok: true, text: "Your Pro plan will end at the end of the current period." }); } catch (e) { setMsg({ ok: false, text: (e as ApiError).message }); } finally { setBusy(null); } };

  return (
    <div className="max-w-6xl mx-auto px-4 py-12">
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-amber-500/10 text-amber-600 text-sm font-medium mb-4"><Crown className="w-4 h-4" /> BuyWise Pro</div>
        <h1 className="text-3xl font-bold mb-3">More tracking. Deeper insight. Same honest data.</h1>
        <p className="text-muted-foreground max-w-2xl mx-auto">Pro pays for the data and compute behind BuyWise. It never changes Trust Scores or rankings.</p>
        <p className="text-sm text-muted-foreground mt-3 inline-flex items-center gap-2"><QrCode className="w-4 h-4 text-indigo-500" /> Pay by UPI, card or netbanking. No auto-renewal: a plan simply ends unless you buy another.</p>
      </div>

      {meta && !meta.payments_enabled && <p className="mb-6 text-sm text-amber-600 flex items-center justify-center gap-2"><AlertTriangle className="w-4 h-4" /> Payments are not configured on this deployment yet (Razorpay keys missing). Plans are shown for reference.</p>}
      {meta && meta.payments_enabled && meta.payments_ready === false && <p className="mb-6 text-sm text-amber-600 flex items-center justify-center gap-2"><AlertTriangle className="w-4 h-4" /> Checkout is unavailable right now: Razorpay is not accepting this site&apos;s payment keys. Nothing you do here can be charged. Please try again later.</p>}
      {msg && <div className={`mb-6 p-3 rounded-xl text-sm border text-center ${msg.ok ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" : "bg-rose-500/10 text-rose-600 border-rose-500/20"}`}>{msg.text}</div>}
      {currentSub?.is_pro && <div className="mb-6 glass rounded-2xl p-4 text-sm flex flex-wrap items-center justify-between gap-3"><span>You are on <strong>{currentSub.plan.replace(/_/g, " ")}</strong>{currentSub.current_period_end ? ` until ${formatDate(currentSub.current_period_end)}` : ""}{currentSub.cancel_at_period_end ? " (cancellation scheduled)" : ""}.</span>{!currentSub.cancel_at_period_end && <button onClick={cancel} disabled={busy === "cancel"} className="px-3 py-1.5 rounded-lg glass text-xs font-medium hover:bg-muted/50">Cancel renewal</button>}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
        {plans.map((p) => {
          const current = currentSub ? (p.id === "free" ? !currentSub.is_pro : currentSub.plan === p.id) : p.id === "free" && !!user;
          const highlight = p.is_best_value;
          return (
            <div key={p.id} className={`glass rounded-2xl p-6 flex flex-col relative ${highlight ? "ring-2 ring-indigo-500/50" : ""}`}>
              {highlight && <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full gradient-primary text-white text-[11px] font-bold uppercase tracking-wide whitespace-nowrap">Best value</div>}
              <h2 className="font-semibold text-lg">{p.name}</h2>

              <div className="my-2">
                <div className="text-3xl font-bold tabular-nums">{p.price_inr ? formatPrice(p.price_inr) : "₹0"}</div>
                <div className="text-sm text-muted-foreground">{p.period_days ? periodLabel(p.period_days) : "always free"}</div>
              </div>

              <div className="h-10 mb-2">
                {p.monthly_equivalent_inr != null && p.period_days > 30 && (
                  <>
                    <div className="text-sm font-medium text-emerald-600 tabular-nums">{formatPrice(p.monthly_equivalent_inr)}/month</div>
                    {p.savings_percent ? <div className="text-xs text-muted-foreground">{p.savings_percent}% less than monthly</div> : null}
                  </>
                )}
              </div>

              <ul className="space-y-1.5 text-sm text-muted-foreground flex-1 mb-4">{p.features.map((f) => <li key={f} className="flex gap-2"><Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />{f}</li>)}</ul>

              {p.id === "free" ? <div className="text-center text-sm text-muted-foreground py-2.5">{current ? "Current plan" : "Included"}</div> : (
                <button onClick={() => checkout(p.id)} disabled={busy === p.id || current || (meta ? !meta.payments_enabled || meta.payments_ready === false : false)} className={`w-full py-2.5 rounded-xl font-medium flex items-center justify-center gap-2 disabled:opacity-50 transition-colors ${highlight ? "gradient-primary text-white" : "glass hover:bg-muted/50"}`}>
                  <QrCode className="w-4 h-4" />
                  {current ? "Current plan" : busy === p.id ? "Opening checkout…" : user ? "Pay by UPI or card" : "Sign in to subscribe"}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className="glass rounded-2xl p-5 mt-8 max-w-3xl mx-auto">
        <h3 className="font-semibold text-sm mb-2 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-indigo-500" /> How payment works</h3>
        <ul className="text-sm text-muted-foreground space-y-1.5">
          <li>Choosing a plan opens Razorpay with UPI first. On a computer you get a QR code to scan with any UPI app; on a phone it opens GPay, PhonePe, Paytm or whichever you use.</li>
          <li>BuyWise never sees your card, UPI ID or bank details. Razorpay handles the payment and tells us only the order, amount and status.</li>
          <li>Pro activates only after our server verifies the payment with Razorpay. A successful-looking screen is never enough on its own.</li>
          <li>Nothing renews automatically. When a plan ends you go back to Free, with your alerts and saved products intact.</li>
        </ul>
      </div>

      <p className="text-xs text-muted-foreground text-center mt-6">Prices include applicable taxes unless stated otherwise at checkout.</p>
    </div>
  );
}
