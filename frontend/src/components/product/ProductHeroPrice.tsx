"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Lock, TrendingDown, TrendingUp, Minus } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPrice, getPriceActionColor, priceActionLabel } from "@/lib/utils";
import ProductActions from "@/components/product/ProductActions";
import { usePriceHistory } from "@/lib/usePriceHistory";
import type { ProductDetail } from "@/lib/types";

/**
 * The lowest price, the buy-or-wait signal and the track/save buttons.
 *
 * All three are rendered in the browser for one reason: the page is built on
 * the server, which cannot see the reader's token because that lives in their
 * browser. Every figure it fetched came back withheld, so a subscriber was
 * shown an advertisement for the plan they had already bought.
 */
export default function ProductHeroPrice({ initial }: { initial: ProductDetail }) {
  const { user, loading: authLoading } = useAuth();
  const viewer = `${user?.id ?? "anon"}:${user?.plan ?? "none"}:${user?.role ?? "none"}:${initial.id}`;
  const [snapshot, setSnapshot] = useState<{ viewer: string; product: ProductDetail } | null>(null);
  const product = snapshot?.viewer === viewer ? snapshot.product : initial;
  const { history } = usePriceHistory(initial.id, 90);

  useEffect(() => {
    if (authLoading) return;
    let live = true;
    api.product(initial.id).then((p) => { if (live) setSnapshot({ viewer, product: p }); }).catch(() => {});
    return () => { live = false; };
  }, [authLoading, viewer, initial.id]);

  const signal = history && !history.locked ? history.signal : null;
  const SignalIcon = signal?.action === "BUY_NOW" ? TrendingDown : signal?.action === "WAIT" ? TrendingUp : Minus;
  const lowest = product.lowest_price ?? null;

  return (
    <>
      {product.locked ? (
        <div className="mb-5">
          <div className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Lock className="w-5 h-5 text-indigo-500" /> Prices with Pro
          </div>
          <p className="text-muted-foreground text-sm">
            Unlock retailer prices, best-value picks and price history for this product.{" "}
            <Link href={`/pricing?source=retailer_comparison&returnTo=${encodeURIComponent(`/product/${product.id}`)}`} className="text-indigo-500 hover:underline">Explore Pro</Link>
          </p>
        </div>
      ) : (
        <>
          <div className="text-4xl font-bold mb-1 tabular-nums">{lowest ? formatPrice(lowest) : "No price yet"}</div>
          <p className="text-muted-foreground text-sm mb-5">
            Lowest estimated final price across exact matches
            {product.highest_price && lowest && product.highest_price > lowest ? ` · up to ${formatPrice(product.highest_price)} elsewhere` : ""}
          </p>
        </>
      )}

      {signal && (
        <div className={`glass rounded-xl p-4 border-l-4 mb-4 ${signal.action === "BUY_NOW" ? "border-emerald-500" : signal.action === "WAIT" ? "border-amber-500" : "border-muted-foreground"}`}>
          <div className="flex items-center gap-2 mb-1">
            <SignalIcon className={`w-5 h-5 ${getPriceActionColor(signal.action)}`} />
            <span className={`font-bold ${getPriceActionColor(signal.action)}`}>{priceActionLabel(signal.action)}</span>
            {signal.action !== "INSUFFICIENT_DATA" && <span className="text-xs text-muted-foreground">({Math.round(signal.confidence * 100)}% confidence)</span>}
          </div>
          <p className="text-sm text-muted-foreground">{signal.reasoning}</p>
        </div>
      )}

      <ProductActions productId={product.id} currentPrice={lowest} />
    </>
  );
}
