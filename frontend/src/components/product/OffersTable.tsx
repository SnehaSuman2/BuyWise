"use client";

import { useState } from "react";
import Link from "next/link";
import { ShieldCheck, ExternalLink, ChevronDown, ChevronUp, Info, Store } from "lucide-react";
import VerificationBadge from "@/components/trust/VerificationBadge";
import { formatPrice, getTrustColor, matchBadgeClass, formatRelativeTime } from "@/lib/utils";
import type { OfferComparison, Offer } from "@/lib/types";
import { track } from "@/lib/analytics";
import LockedPanel from "@/components/product/LockedPanel";

function PriceBreakdown({ o }: { o: Offer }) {
  const p = o.price;
  const row = (label: string, value: React.ReactNode, muted = false) => (
    <div className={`flex justify-between gap-4 ${muted ? "text-muted-foreground" : ""}`}><span>{label}</span><span className="font-medium tabular-nums">{value}</span></div>
  );
  return (
    <div className="text-sm space-y-1 max-w-md">
      {p.original_price && row("List price (MRP)", <span className="line-through text-muted-foreground">{formatPrice(p.original_price)}</span>, true)}
      {p.discount_amount ? row("Known discount (already applied)", <span className="text-emerald-500">−{formatPrice(p.discount_amount)}{p.discount_percent ? ` (${p.discount_percent}%)` : ""}</span>) : null}
      {row("Product price", formatPrice(p.listed_price))}
      {row("Shipping", p.shipping_known ? (p.shipping_price ? formatPrice(p.shipping_price) : <span className="text-emerald-500">Free</span>) : <span className="text-amber-500">Unknown</span>)}
      {p.coupon_code || p.coupon_amount ? row(`Coupon${p.coupon_code ? ` ${p.coupon_code}` : ""}`, p.coupon_amount ? <span className="text-emerald-500">−{formatPrice(p.coupon_amount)}</span> : "amount unknown") : row("Coupons", <span className="text-muted-foreground">none known</span>, true)}
      <div className="flex justify-between gap-4 border-t border-border/40 pt-1 font-semibold"><span>{p.final_price_known ? "Final observed price" : "Estimated final price"}</span><span className="tabular-nums">{formatPrice(p.estimated_final_price)}</span></div>
      {p.notes.map((n) => <p key={n} className="text-xs text-amber-600 flex gap-1"><Info className="w-3 h-3 mt-0.5 shrink-0" />{n}</p>)}
      {!p.final_price_known && !p.notes.length && <p className="text-xs text-muted-foreground">Final price may vary at checkout.</p>}
      <p className="text-xs text-muted-foreground">Source: {o.source_provider}{o.source_engine ? ` · ${o.source_engine}` : ""} · observed {formatRelativeTime(o.observed_at)}</p>
      {o.match.reasons.length > 0 && <p className="text-xs text-muted-foreground">Match: {o.match.reasons.join("; ")}</p>}
    </div>
  );
}

export default function OffersTable({ comparison }: { comparison: OfferComparison }) {
  const [open, setOpen] = useState<string | null>(null);
  const cheapestId = comparison.picks.find((p) => p.category === "CHEAPEST")?.offer_id;
  const bestId = comparison.picks.find((p) => p.category === "BEST_OVERALL")?.offer_id;
  if (!comparison.offers.length) return <p className="text-sm text-muted-foreground p-6">No offers recorded yet for this product.</p>;
  return (
    <div className="overflow-x-auto">
      {comparison.locked && (
        <div className="px-4 pt-4 pb-2 text-xs text-muted-foreground">Lowest price found. The comparison across every retailer is part of Pro.</div>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/40 text-muted-foreground">
            <th className="text-left py-3 px-4 font-medium">Retailer / seller</th>
            <th className="text-right py-3 px-4 font-medium">Price</th>
            <th className="text-right py-3 px-4 font-medium hidden sm:table-cell">Shipping</th>
            <th className="text-right py-3 px-4 font-medium">Est. final</th>
            <th className="text-center py-3 px-4 font-medium hidden md:table-cell">Trust</th>
            <th className="text-center py-3 px-4 font-medium hidden lg:table-cell">Match</th>
            <th className="text-center py-3 px-4 font-medium hidden lg:table-cell">Delivery</th>
            <th className="py-3 px-2"></th>
          </tr>
        </thead>
        <tbody>
          {comparison.offers.map((o) => {
            const isOpen = open === o.id;
            return (
              <>
                <tr key={o.id} className={`border-b border-border/20 hover:bg-muted/30 transition-colors ${o.id === bestId ? "bg-indigo-500/5" : o.id === cheapestId ? "bg-emerald-500/5" : ""} ${o.match.match_type !== "exact_match" ? "opacity-80" : ""}`}>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-muted/50 flex items-center justify-center shrink-0"><Store className="w-4 h-4 text-muted-foreground" /></div>
                      <div className="min-w-0">
                        <Link href={`/retailer/${o.retailer.id}`} className="font-medium hover:text-indigo-500">{o.retailer.name}</Link>
                        {o.seller && o.seller.name !== o.retailer.name && <div className="text-xs text-muted-foreground truncate">Sold by {o.seller.name}</div>}
                        <VerificationBadge verification={o.trust.verification} className="mt-0.5" />
                        <div className="flex gap-1 mt-0.5">
                          {o.id === bestId && <span className="text-[10px] font-semibold text-indigo-500">BEST OVERALL</span>}
                          {o.id === cheapestId && o.id !== bestId && <span className="text-[10px] font-semibold text-emerald-500">CHEAPEST</span>}
                          {o.availability === "out_of_stock" && <span className="text-[10px] font-semibold text-rose-500">OUT OF STOCK</span>}
                          {o.condition !== "new" && <span className="text-[10px] font-semibold text-amber-500 uppercase">{o.condition}</span>}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right tabular-nums">
                    <div className="font-semibold">{formatPrice(o.price.listed_price)}</div>
                    {o.price.original_price && <div className="text-xs text-muted-foreground line-through">{formatPrice(o.price.original_price)}</div>}
                  </td>
                  <td className="py-3 px-4 text-right hidden sm:table-cell tabular-nums">{o.price.shipping_known ? (o.price.shipping_price ? formatPrice(o.price.shipping_price) : <span className="text-emerald-500">Free</span>) : <span className="text-amber-500 text-xs">unknown</span>}</td>
                  <td className="py-3 px-4 text-right tabular-nums">
                    <div className="font-bold text-base">{formatPrice(o.price.estimated_final_price)}</div>
                    {!o.price.final_price_known && <div className="text-[10px] text-amber-600">may vary at checkout</div>}
                  </td>
                  <td className="py-3 px-4 text-center hidden md:table-cell">
                    {typeof o.trust.score === "number" ? (
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-bold ${getTrustColor(o.trust.score)}`}><ShieldCheck className="w-3 h-3" />{o.trust.score}</span>
                    ) : (
                      <span className="text-xs text-muted-foreground" title="Not assessed yet — BuyWise is gathering evidence about this seller.">Not rated</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-center hidden lg:table-cell">
                    <span className={`inline-block px-2 py-0.5 rounded-md border text-[11px] font-medium ${matchBadgeClass(o.match.match_type)}`} title={o.match.reasons.join("; ")}>{o.match.label} · {Math.round(o.match.confidence * 100)}%</span>
                  </td>
                  <td className="py-3 px-4 text-center hidden lg:table-cell text-muted-foreground text-xs">{o.delivery_days !== null && o.delivery_days !== undefined ? `${o.delivery_days} day${o.delivery_days === 1 ? "" : "s"}` : o.delivery_text || "—"}</td>
                  <td className="py-3 px-2 text-right whitespace-nowrap">
                    <button onClick={() => setOpen(isOpen ? null : o.id)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground" aria-label="Show price breakdown" aria-expanded={isOpen}>{isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}</button>
                    <a href={o.go_url} target="_blank" rel="noopener noreferrer sponsored" onClick={() => track("retailer_click", { retailer: o.retailer?.name, product_id: comparison.product_id, match_type: o.match?.match_type })} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-500/10 text-indigo-500 text-xs font-medium hover:bg-indigo-500/20 transition-colors ml-1">Visit <ExternalLink className="w-3 h-3" /></a>
                  </td>
                </tr>
                {isOpen && (
                  <tr key={`${o.id}-details`} className="bg-muted/20 border-b border-border/20"><td colSpan={8} className="px-6 py-4"><PriceBreakdown o={o} /></td></tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
      {comparison.locked && (
        <div className="p-4"><LockedPanel hiddenOffers={comparison.hidden_offers} hiddenRetailers={comparison.hidden_retailers} what="the full comparison" /></div>
      )}
      <p className="px-4 py-3 text-xs text-muted-foreground">Sorted by estimated final price. Only exact matches are used for picks; variants and similar products are shown for context. Prices can differ by pincode and change at checkout. Sellers marked <strong>Unverified</strong> have not been assessed yet — BuyWise gathers evidence on them in the background, and merchants it assesses as high risk are withheld entirely. Sellers are never able to pay for inclusion or a better score.</p>
    </div>
  );
}
