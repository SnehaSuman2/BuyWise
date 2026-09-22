"use client";

import Link from "next/link";
import { Lock, Crown } from "lucide-react";
import { useAuth } from "@/lib/auth";

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
        Pro shows every retailer side by side with true final prices, price history, trust scores and the best overall, cheapest and safest picks. From ₹99 a month, and nothing renews by itself.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Link href="/pricing" className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">See Pro plans</Link>
        {!user && <Link href="/login?next=/pricing" className="px-4 py-2 rounded-xl glass text-sm">Sign in</Link>}
      </div>
    </div>
  );
}
