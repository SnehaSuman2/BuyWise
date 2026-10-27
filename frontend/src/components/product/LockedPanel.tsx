"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { LockKeyhole, ArrowRight, Check, Crown } from "lucide-react";
import { api } from "@/lib/api";
import { track } from "@/lib/analytics";
import { formatPrice } from "@/lib/utils";
import type { PlanInfo } from "@/lib/types";

let plansPromise: Promise<PlanInfo[]> | null = null;
function loadPlans(): Promise<PlanInfo[]> {
  if (!plansPromise) plansPromise = api.plans().catch(() => { plansPromise = null; return []; });
  return plansPromise;
}
function priceSentence(plans: PlanInfo[]): string | null {
  const paid = plans.filter(p => p.price_inr > 0);
  if (!paid.length) return null;
  const entry = paid.reduce((a, b) => a.price_inr <= b.price_inr ? a : b);
  return `${formatPrice(entry.price_inr)} for ${entry.period_days} days. One payment. No automatic renewal.`;
}
const previews = {
  recommendations: { title: "Your best place to buy, explained", text: "Unlock the best overall, cheapest and safest picks, with the reasons behind each recommendation.", items: ["Best overall", "Cheapest", "Safest seller"] },
  price_history: { title: "Is this a good time to buy?", text: "Unlock recorded price trends, historical lows and buy/wait guidance when there is enough data.", items: ["Recorded prices", "Historical low", "Buy or wait"] },
  retailer_comparison: { title: "One product. The full retailer comparison.", text: "Unlock retailer prices, known delivery charges and discounts side by side before you choose where to buy.", items: ["Retailer prices", "Known charges", "Offer rankings"] },
};

export default function LockedPanel({ hiddenOffers, hiddenRetailers, what = "the full comparison", feature, placement = "product" }: {
  hiddenOffers?: number; hiddenRetailers?: number; what?: string;
  feature?: keyof typeof previews; placement?: "product" | "search" | "family";
}) {
  const pathname = usePathname();
  const ref = useRef<HTMLDivElement>(null);
  const [pricing, setPricing] = useState<string | null>(null);
  const selected = feature ?? (what.includes("history") ? "price_history" : what.includes("decision") ? "recommendations" : "retailer_comparison");
  const copy = previews[selected];
  const href = `/pricing?source=${selected}&returnTo=${encodeURIComponent(pathname)}`;
  useEffect(() => {
    let live = true;
    loadPlans().then(plans => { if (live) setPricing(priceSentence(plans)); });
    return () => { live = false; };
  }, []);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        track("pro_gate_view", { feature: selected, placement });
        observer.disconnect();
      }
    }, { threshold: 0.4 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [selected, placement]);
  return <div ref={ref} className="rounded-2xl border border-indigo-500/25 bg-gradient-to-br from-indigo-500/5 via-purple-500/5 to-transparent p-5 sm:p-7">
    <div className="flex items-start gap-4">
      <span className="w-11 h-11 shrink-0 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center"><LockKeyhole size={21} /></span>
      <div className="min-w-0"><p className="text-[11px] font-semibold text-indigo-500 tracking-wider uppercase mb-2 flex items-center gap-1.5"><Crown size={13} /> BuyWise Pro</p><h3 className="text-lg sm:text-xl font-semibold">{copy.title}</h3><p className="text-sm text-muted-foreground leading-relaxed mt-2 max-w-xl">{copy.text}</p></div>
    </div>
    {Boolean(hiddenOffers) && <p className="mt-4 text-sm font-medium">{hiddenOffers} offer{hiddenOffers === 1 ? "" : "s"}{hiddenRetailers ? ` across ${hiddenRetailers} retailer${hiddenRetailers === 1 ? "" : "s"}` : ""} available to unlock.</p>}
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 my-5" aria-label="Included Pro insights">{copy.items.map(item => <div key={item} className="rounded-xl border border-border/50 bg-background/70 px-3 py-3 text-xs flex items-center gap-2"><Check size={14} className="text-indigo-500 shrink-0" />{item}<LockKeyhole size={12} className="ml-auto shrink-0 text-muted-foreground" /></div>)}</div>
    <div className="flex flex-wrap items-center gap-3"><Link href={href} onClick={() => track("pro_upgrade_click", { feature: selected, placement })} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700">Unlock with Pro <ArrowRight size={16} /></Link><p className="text-xs text-muted-foreground">{pricing ?? "See plans and what’s included."}</p></div>
  </div>;
}
