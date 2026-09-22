"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Lock, Crown } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPrice } from "@/lib/utils";
import type { PlanInfo } from "@/lib/types";

/**
 * The plans, fetched once and shared by every locked panel on a page.
 *
 * The price used to be written into this sentence by hand, which put "from ₹99
 * a month" in front of shoppers when the yearly plan had made the real floor
 * ₹66. A price quoted to a shopper has to come from the same place the
 * checkout charges from, so it cannot drift again.
 */
let plansPromise: Promise<PlanInfo[]> | null = null;
function loadPlans(): Promise<PlanInfo[]> {
  if (!plansPromise) plansPromise = api.plans().catch(() => []);
  return plansPromise;
}

function priceSentence(plans: PlanInfo[]): string | null {
  const paid = plans.filter((p) => p.price_inr > 0);
  if (!paid.length) return null;
  const cheapestMonthly = Math.min(
    ...paid.map((p) => p.monthly_equivalent_inr ?? p.price_inr),
  );
  const best = paid.find(
    (p) => (p.monthly_equivalent_inr ?? p.price_inr) === cheapestMonthly,
  );
  const entry = paid.reduce((a, b) => (a.price_inr <= b.price_inr ? a : b));
  const months = best ? Math.round(best.period_days / 30) : 0;
  // Only call it a monthly rate when a longer plan actually beats the shortest.
  if (best && months > 1 && cheapestMonthly < entry.price_inr) {
    return `From ${formatPrice(cheapestMonthly)} a month on the ${months}-month plan, or ${formatPrice(entry.price_inr)} for one month.`;
  }
  return `From ${formatPrice(entry.price_inr)}.`;
}

/**
 * Shown where the retailer comparison or the picks would be, for viewers who
 * are not on Pro. The server has already withheld the data; this only explains.
 */
export default function LockedPanel({
  hiddenOffers,
  hiddenRetailers,
  what = "the full comparison",
}: {
  hiddenOffers?: number;
  hiddenRetailers?: number;
  what?: string;
}) {
  const { user } = useAuth();
  const [pricing, setPricing] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    loadPlans().then((plans) => {
      if (live) setPricing(priceSentence(plans));
    });
    return () => {
      live = false;
    };
  }, []);

  const count =
    hiddenOffers && hiddenRetailers
      ? `${hiddenOffers} more offer${hiddenOffers === 1 ? "" : "s"} across ${hiddenRetailers} other retailer${hiddenRetailers === 1 ? "" : "s"}`
      : hiddenOffers
        ? `${hiddenOffers} more offer${hiddenOffers === 1 ? "" : "s"}`
        : null;
  return (
    <div className="relative rounded-2xl border border-dashed border-indigo-500/40 bg-indigo-500/5 p-6 text-center">
      <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-indigo-500/10 text-indigo-500 mb-3"><Lock className="w-5 h-5" /></div>
      <h3 className="font-semibold mb-1 flex items-center justify-center gap-2"><Crown className="w-4 h-4 text-amber-500" /> {count ? `${count} with Pro` : `${what[0].toUpperCase()}${what.slice(1)} is part of Pro`}</h3>
      <p className="text-sm text-muted-foreground max-w-md mx-auto mb-4">
        Pro shows every retailer side by side with true final prices, price history, trust scores and the best overall, cheapest and safest picks.
        {/* No price is claimed until the server has said what it is. */}
        {pricing ? ` ${pricing}` : ""} Nothing renews by itself.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Link href="/pricing" className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">See Pro plans</Link>
        {!user && <Link href="/login?next=/pricing" className="px-4 py-2 rounded-xl glass text-sm">Sign in</Link>}
      </div>
    </div>
  );
}
