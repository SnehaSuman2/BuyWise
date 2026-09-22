"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, ShieldCheck, Store, Layers, ArrowUpRight, Lock, BadgeCheck } from "lucide-react";
import { specSummary } from "@/lib/specs";
import { formatPrice, getTrustColor, formatRelativeTime } from "@/lib/utils";
import LockedPanel from "@/components/product/LockedPanel";
import type { ProductFamily, FamilyVariant } from "@/lib/types";
import { track } from "@/lib/analytics";

function titleCase(s: string) {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

function pickDefault(family: ProductFamily): FamilyVariant | null {
  if (!family.variants.length) return null;
  if (family.selected_storage) {
    const chosen = family.variants.find((v) => v.storage === family.selected_storage);
    if (chosen) return chosen;
  }
  return [...family.variants].sort((a, b) => b.offer_count - a.offer_count)[0];
}

/**
 * One product line, every storage size, every store. The server has already
 * sorted each variant's offers cheapest first and withheld them for viewers
 * without Pro; this only lets the shopper pick the size and colour.
 */
export default function FamilyPanel({ family, compact = false }: { family: ProductFamily; compact?: boolean }) {
  const [storage, setStorage] = useState<string | null | undefined>(() => pickDefault(family)?.storage);
  const [color, setColor] = useState<string | null>(null);
  const variant = family.variants.find((v) => v.storage === storage) ?? pickDefault(family);
  if (!variant) return null;
  const rows = color ? variant.offers.filter((o) => o.color === color) : variant.offers;
  const cheapestNew = rows.find((o) => o.condition === "new") ?? rows[0];
  const sizes = family.variants.filter((v) => v.storage).length;

  return (
    <section className="glass rounded-2xl p-5 sm:p-6 mb-8 animate-fade-in" aria-label={`${family.label} across stores`}>
      <div className="flex flex-col sm:flex-row sm:items-start gap-4 mb-5">
        {family.image && (
          <img src={family.image} alt={family.label} className="w-20 h-20 rounded-xl object-cover bg-muted/30 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="text-xs text-indigo-500 font-medium mb-1 flex items-center gap-1"><Layers className="w-3.5 h-3.5" /> Every store, one place{family.brand ? ` · ${family.brand}` : ""}</div>
          <h2 className="text-2xl font-bold leading-tight">{family.label}</h2>
          {family.curated && family.specs && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-sm">
              {specSummary(family.specs).map((part) => <span key={part} className="text-foreground/80">{part}</span>)}
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground" title={family.specs_note || undefined}><BadgeCheck className="w-3.5 h-3.5 text-indigo-500" /> Curated specs</span>
            </div>
          )}
          <p className="text-sm text-muted-foreground mt-1">
            {family.locked
              ? family.hint
              : `${family.total_retailers} store${family.total_retailers === 1 ? "" : "s"} · ${family.total_offers} offer${family.total_offers === 1 ? "" : "s"}${sizes > 1 ? ` · ${sizes} storage sizes` : ""}. Pick a size and colour; stores are listed cheapest first.`}
          </p>
        </div>
        {compact && (
          <Link href={`/family/${encodeURIComponent(family.line)}`} className="inline-flex items-center gap-1 text-sm font-medium text-indigo-500 hover:underline shrink-0">Open full view <ArrowUpRight className="w-4 h-4" /></Link>
        )}
      </div>

      <div className="mb-4">
        <div className="text-xs font-medium text-muted-foreground mb-2">Storage</div>
        <div className="flex flex-wrap gap-2">
          {family.variants.map((v) => {
            const active = v.storage === variant.storage;
            return (
              <button key={v.label} type="button" onClick={() => { setStorage(v.storage); setColor(null); }} className={`px-3 py-2 rounded-xl text-sm border transition-colors text-left ${active ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40 hover:bg-muted/50"}`} aria-pressed={active}>
                <div className="font-semibold">{v.label}{v.official === false && v.storage ? <span className="ml-1 text-[10px] font-normal text-muted-foreground" title="A size seen in listings that the maker's catalogue does not list">(listed)</span> : null}</div>
                <div className="text-[11px] text-muted-foreground">
                  {family.locked ? `${v.retailer_count} store${v.retailer_count === 1 ? "" : "s"}` : v.lowest_price ? `from ${formatPrice(v.lowest_price)}` : "no price yet"}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {variant.colors.length > 0 && (
        <div className="mb-5">
          <div className="text-xs font-medium text-muted-foreground mb-2">Colour</div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setColor(null)} className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${color === null ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40 hover:bg-muted/50"}`} aria-pressed={color === null}>All colours</button>
            {variant.colors.map((c) => (
              <button key={c} type="button" onClick={() => setColor(c)} className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${color === c ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40 hover:bg-muted/50"}`} aria-pressed={color === c}>{titleCase(c)}</button>
            ))}
          </div>
        </div>
      )}

      {family.locked ? (
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3"><Lock className="w-4 h-4 text-indigo-500" /> {variant.offer_count} offer{variant.offer_count === 1 ? "" : "s"} from {variant.retailer_count} store{variant.retailer_count === 1 ? "" : "s"} for {variant.label}{variant.colors.length ? ` in ${variant.colors.length} colour${variant.colors.length === 1 ? "" : "s"}` : ""}.</div>
          <LockedPanel hiddenOffers={variant.offer_count} hiddenRetailers={variant.retailer_count} what="the store-by-store comparison" />
        </div>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground py-4">No store has a price recorded for this {color ? "colour" : "size"} yet. Open a product below and BuyWise fetches its stores.</p>
      ) : (
        <div className="overflow-x-auto -mx-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/40 text-muted-foreground">
                <th className="text-left py-2 px-2 font-medium">Store</th>
                <th className="text-left py-2 px-2 font-medium hidden sm:table-cell">Colour</th>
                <th className="text-right py-2 px-2 font-medium">Est. final price</th>
                <th className="text-center py-2 px-2 font-medium hidden md:table-cell">Trust</th>
                <th className="text-left py-2 px-2 font-medium hidden lg:table-cell">Delivery</th>
                <th className="py-2 px-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => {
                const diff = cheapestNew ? o.price - cheapestNew.price : 0;
                const isCheapest = cheapestNew && o.offer_id === cheapestNew.offer_id;
                return (
                  <tr key={o.offer_id} className={`border-b border-border/20 hover:bg-muted/30 transition-colors ${isCheapest ? "bg-emerald-500/5" : ""} ${o.condition !== "new" ? "opacity-80" : ""}`}>
                    <td className="py-3 px-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-8 h-8 rounded-lg bg-muted/50 flex items-center justify-center shrink-0"><Store className="w-4 h-4 text-muted-foreground" /></div>
                        <div className="min-w-0">
                          <Link href={`/retailer/${o.retailer_id}`} className="font-medium hover:text-indigo-500">{o.retailer_name}</Link>
                          {o.seller_name && o.seller_name !== o.retailer_name && <div className="text-xs text-muted-foreground truncate">Sold by {o.seller_name}</div>}
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {isCheapest && <span className="text-[10px] font-semibold text-emerald-500">CHEAPEST</span>}
                            {o.condition !== "new" && <span className="text-[10px] font-semibold text-amber-500 uppercase">{o.condition}</span>}
                            {o.above_market && <span className="text-[10px] font-semibold text-rose-500" title="Priced well above the other stores listed here for the same size">ABOVE OTHER STORES</span>}
                            {o.availability === "out_of_stock" && <span className="text-[10px] font-semibold text-rose-500">OUT OF STOCK</span>}
                            {o.is_demo && <span className="text-[10px] font-semibold text-amber-500">DEMO</span>}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-2 hidden sm:table-cell text-muted-foreground">{o.color ? titleCase(o.color) : "—"}</td>
                    <td className="py-3 px-2 text-right tabular-nums">
                      <div className="font-bold text-base">{formatPrice(o.price)}</div>
                      {diff > 0 && <div className="text-[11px] text-muted-foreground">+{formatPrice(diff)} vs cheapest</div>}
                      {!o.final_price_known && <div className="text-[10px] text-amber-600">may vary at checkout</div>}
                    </td>
                    <td className="py-3 px-2 text-center hidden md:table-cell">
                      {typeof o.trust_score === "number" ? (
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-bold ${getTrustColor(o.trust_score)}`}><ShieldCheck className="w-3 h-3" />{o.trust_score}</span>
                      ) : (
                        <span className="text-xs text-muted-foreground">Not rated</span>
                      )}
                    </td>
                    <td className="py-3 px-2 hidden lg:table-cell text-xs text-muted-foreground">{o.delivery_days !== null && o.delivery_days !== undefined ? `${o.delivery_days} day${o.delivery_days === 1 ? "" : "s"}` : o.delivery_text || "—"}<div>seen {formatRelativeTime(o.observed_at)}</div></td>
                    <td className="py-3 px-2 text-right whitespace-nowrap">
                      <Link href={`/product/${o.product_id}`} className="text-xs text-muted-foreground hover:text-foreground mr-2">Details</Link>
                      <a href={o.go_url} target="_blank" rel="noopener noreferrer sponsored" onClick={() => track("retailer_click", { retailer: o.retailer_name, product_id: o.product_id, match_type: "exact_match" })} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-500/10 text-indigo-500 text-xs font-medium hover:bg-indigo-500/20 transition-colors">Visit <ExternalLink className="w-3 h-3" /></a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="px-2 pt-3 text-xs text-muted-foreground">{family.specs_note ? `${family.specs_note} ` : ""}Sorted by estimated final price; refurbished and used items follow new ones. &ldquo;Above other stores&rdquo; compares a price only with the other stores listed here for the same size. Prices differ by colour and pincode and can change at checkout.</p>
        </div>
      )}
    </section>
  );
}
