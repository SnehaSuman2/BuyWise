import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Star, TrendingDown, TrendingUp, Minus, Award, IndianRupee, Shield, Sparkles, Info } from "lucide-react";
import { serverGet } from "@/lib/api";
import { formatPrice, getPriceActionColor, priceActionLabel, priceStatusLabel, getTrustColor, riskLabel } from "@/lib/utils";
import DataBadge from "@/components/ui/DataBadge";
import SafeText from "@/components/ui/SafeText";
import OffersTable from "@/components/product/OffersTable";
import RecommendationCards from "@/components/product/RecommendationCards";
import PriceHistoryChart from "@/components/product/PriceHistoryChart";
import ProductActions from "@/components/product/ProductActions";
import TrustScoreCard from "@/components/trust/TrustScoreCard";
import type { OfferComparison, PriceHistoryData, ProductDetail, RecommendationSet, TrustScoreData } from "@/lib/types";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const product = await serverGet<ProductDetail>(`/products/${id}`);
  if (!product) return { title: "Product not found" };
  const desc = `Compare ${product.offer_count} offers for ${product.name}${product.lowest_price ? ` from ${formatPrice(product.lowest_price)}` : ""}. True prices, Trust Scores and price history on BuyWise.`;
  return {
    title: product.name,
    description: desc,
    alternates: { canonical: `/product/${product.id}` },
    openGraph: { title: product.name, description: desc, images: product.images?.[0] ? [product.images[0]] : undefined, url: `${APP_URL}/product/${product.id}` },
    robots: product.is_demo ? { index: false, follow: false } : undefined,
  };
}

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [product, offers, history, recs, trusts] = await Promise.all([
    serverGet<ProductDetail>(`/products/${id}`),
    serverGet<OfferComparison>(`/products/${id}/offers`),
    serverGet<PriceHistoryData>(`/products/${id}/history?days=90`),
    serverGet<RecommendationSet>(`/products/${id}/recommendations`),
    serverGet<TrustScoreData[]>(`/products/${id}/trust`),
  ]);
  if (!product) notFound();

  const best = recs?.recommendations.find((r) => r.category === "BEST_OVERALL") ?? null;
  const signal = history?.signal ?? null;
  const bestTrust = best ? trusts?.find((t) => t.retailer_id === best.retailer_id) ?? null : null;
  const lowest = offers?.lowest_final_price ?? product.lowest_price ?? null;
  const SignalIcon = signal?.action === "BUY_NOW" ? TrendingDown : signal?.action === "WAIT" ? TrendingUp : Minus;

  const jsonLd = !product.is_demo ? {
    "@context": "https://schema.org", "@type": "Product", name: product.name, brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined, image: product.images, sku: product.mpn || undefined, gtin: product.gtin || undefined,
    offers: offers?.offers.filter((o) => o.match.match_type === "exact_match").map((o) => ({ "@type": "Offer", price: o.price.estimated_final_price, priceCurrency: "INR", availability: o.availability === "out_of_stock" ? "https://schema.org/OutOfStock" : "https://schema.org/InStock", seller: { "@type": "Organization", name: o.retailer.name }, url: `${APP_URL}/product/${product.id}` })),
  } : null;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {jsonLd && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />}

      <section className="grid grid-cols-1 md:grid-cols-5 gap-8 mb-12 animate-fade-in">
        <div className="md:col-span-2 aspect-square rounded-2xl overflow-hidden bg-muted/20 glass">
                    <img src={product.images?.[0] || "https://placehold.co/600x600/1a1a2e/e0e0e0?text=No+image"} alt={product.name} className="w-full h-full object-cover" />
        </div>
        <div className="md:col-span-3 flex flex-col justify-center">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-sm text-indigo-500 font-medium">{[product.brand, product.category].filter(Boolean).join(" · ")}</span>
            <DataBadge meta={product.meta} />
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold mb-3">{product.name}</h1>
          <div className="flex flex-wrap items-center gap-4 mb-4 text-sm text-muted-foreground">
            {product.average_rating ? <span className="flex items-center gap-1"><Star className="w-4 h-4 text-amber-500 fill-current" /><strong className="text-foreground">{product.average_rating}</strong>{product.rating_count ? ` (${product.rating_count.toLocaleString("en-IN")} ratings)` : ""}</span> : null}
            <span>{product.exact_offer_count} exact-match offer{product.exact_offer_count === 1 ? "" : "s"}{product.offer_count > product.exact_offer_count ? ` · ${product.offer_count - product.exact_offer_count} variant/similar` : ""}</span>
            {(product.gtin || product.mpn || product.asin) && <span className="text-xs">ID: {product.gtin || product.mpn || product.asin}</span>}
          </div>
          <div className="text-4xl font-bold mb-1 tabular-nums">{lowest ? formatPrice(lowest) : "No price yet"}</div>
          <p className="text-muted-foreground text-sm mb-5">Lowest estimated final price across exact matches{product.highest_price && lowest && product.highest_price > lowest ? ` · up to ${formatPrice(product.highest_price)} elsewhere` : ""}</p>

          {best && (
            <div className="glass rounded-2xl p-4 mb-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <div className="text-[11px] font-semibold text-indigo-500 uppercase tracking-wide mb-1 flex items-center gap-1"><Award className="w-3 h-3" /> Best overall</div>
                <div className="font-semibold">{best.retailer_name}</div>
                <div className="text-xl font-bold tabular-nums">{formatPrice(best.price)}</div>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-1 flex items-center gap-1"><Shield className="w-3 h-3" /> Trust Score</div>
                <div className={`text-xl font-bold ${getTrustColor(best.trust_score)}`}>{typeof best.trust_score === "number" ? `${best.trust_score}/100` : "—"}</div>
                <div className="text-xs text-muted-foreground">{riskLabel(best.trust_risk)}{bestTrust ? ` · ${bestTrust.confidence_level} confidence` : ""}</div>
              </div>
              <div>
                <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide mb-1 flex items-center gap-1"><IndianRupee className="w-3 h-3" /> Price status</div>
                <div className={`text-xl font-bold ${signal ? getPriceActionColor(signal.action) : ""}`}>{signal ? priceStatusLabel(signal.status) : "—"}</div>
                <div className="text-xs text-muted-foreground">{history?.stats?.percent_vs_average != null ? `${Math.abs(history.stats.percent_vs_average)}% ${history.stats.percent_vs_average < 0 ? "below" : "above"} 90-day avg` : "Not enough BuyWise history yet"}</div>
              </div>
            </div>
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
        </div>
      </section>

      <nav className="flex gap-1 overflow-x-auto mb-8 pb-2 border-b border-border/40" aria-label="Sections">
        {[["recommendation", "Recommendation"], ["offers", "Compare offers"], ["history", "Price history"], ["trust", "Trust"]].map(([id, label]) => (
          <a key={id} href={`#${id}`} className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 whitespace-nowrap transition-colors">{label}</a>
        ))}
      </nav>

      <section id="recommendation" className="mb-16">
        <div className="flex flex-wrap items-center gap-3 mb-6"><h2 className="text-2xl font-bold flex items-center gap-2"><Award className="w-6 h-6 text-indigo-500" /> Shopping decision</h2>{recs && <DataBadge meta={recs.meta} />}</div>
        {recs ? <RecommendationCards recommendations={recs.recommendations} /> : <p className="text-sm text-muted-foreground">Recommendations unavailable right now.</p>}
        {recs?.ai_explanation && (
          <div className="glass rounded-2xl p-5 mt-6">
            <div className="flex items-center gap-2 text-sm font-semibold mb-2"><Sparkles className="w-4 h-4 text-indigo-500" /> AI recommendation <span className="text-xs font-normal text-muted-foreground">({recs.ai_provider === "demo" ? "template explanation — AI provider not configured" : `explained by ${recs.ai_provider}, grounded in the data above`})</span></div>
            <SafeText text={recs.ai_explanation} className="text-sm" />
          </div>
        )}
      </section>

      <section id="offers" className="mb-16">
        <div className="flex flex-wrap items-center gap-3 mb-6"><h2 className="text-2xl font-bold flex items-center gap-2"><IndianRupee className="w-6 h-6 text-emerald-500" /> Compare offers</h2>{offers && <DataBadge meta={offers.meta} />}</div>
        {offers?.meta.warnings.map((w) => <p key={w} className="text-sm text-amber-600 mb-2 flex gap-2"><Info className="w-4 h-4 mt-0.5" />{w}</p>)}
        <div className="glass rounded-2xl overflow-hidden">{offers ? <OffersTable comparison={offers} /> : <p className="p-6 text-sm text-muted-foreground">Offers temporarily unavailable.</p>}</div>
      </section>

      <section id="history" className="mb-16">
        <div className="flex flex-wrap items-center gap-3 mb-6"><h2 className="text-2xl font-bold flex items-center gap-2"><TrendingDown className="w-6 h-6 text-purple-500" /> Price history</h2>{history && <DataBadge meta={history.meta} />}</div>
        {history?.stats ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              {[
                { label: "Current lowest", value: formatPrice(history.stats.current_price) },
                { label: "30-day average", value: history.stats.average_30d ? formatPrice(history.stats.average_30d) : "—" },
                { label: "90-day average", value: history.stats.average_90d ? formatPrice(history.stats.average_90d) : "—" },
                { label: "Recorded low / high", value: `${formatPrice(history.stats.historical_low)} / ${formatPrice(history.stats.historical_high)}` },
              ].map((s) => <div key={s.label} className="glass rounded-xl p-4 text-center"><div className="text-xs text-muted-foreground mb-1">{s.label}</div><div className="text-lg font-bold tabular-nums">{s.value}</div></div>)}
            </div>
            <div className="glass rounded-2xl p-4"><PriceHistoryChart data={history} /></div>
            <p className="text-xs text-muted-foreground mt-3">{history.stats.observations} daily observations over {history.stats.span_days} days · trend: {history.stats.trend}. {history.message}</p>
          </>
        ) : (
          <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">{history?.message || "Price history unavailable for this product."}</div>
        )}
      </section>

      <section id="trust" className="mb-16">
        <h2 className="text-2xl font-bold mb-6 flex items-center gap-2"><Shield className="w-6 h-6 text-blue-500" /> Retailer trust</h2>
        {trusts && trusts.length ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {trusts.map((t) => <TrustScoreCard key={t.retailer_id || t.subject_name} trust={t} compact />)}
          </div>
        ) : <p className="text-sm text-muted-foreground">Not enough evidence to confidently assess these retailers yet.</p>}
        <p className="text-xs text-muted-foreground mt-4">Open a retailer to inspect factors, concerns and the evidence behind each score. <Link href="/trust-methodology" className="text-indigo-500 hover:underline">Methodology</Link></p>
      </section>
    </div>
  );
}
