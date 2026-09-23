import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Star, Shield, ThumbsUp, ThumbsDown, MessagesSquare } from "lucide-react";
import { serverGet } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import DataBadge from "@/components/ui/DataBadge";
import ComparisonSections from "@/components/product/ComparisonSections";
import PriceHistorySection from "@/components/product/PriceHistorySection";
import ProductHeroPrice from "@/components/product/ProductHeroPrice";
import ProductGallery from "@/components/product/ProductGallery";
import TrustScoreCard from "@/components/trust/TrustScoreCard";
import CommunityReviews from "@/components/community/CommunityReviews";
import type { ProductDetail, ReviewAnalysis, TrustScoreData } from "@/lib/types";

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
  // Only what the page shell needs. Offers, recommendations and price history
  // are all fetched in the browser, where the reader's token exists: fetching
  // them here as well cost seconds and returned a withheld answer regardless.
  const [product, trusts, reviews] = await Promise.all([
    serverGet<ProductDetail>(`/products/${id}`),
    serverGet<TrustScoreData[]>(`/products/${id}/trust`),
    serverGet<ReviewAnalysis>(`/products/${id}/reviews`),
  ]);
  if (!product) notFound();


  const jsonLd = !product.is_demo ? {
    "@context": "https://schema.org", "@type": "Product", name: product.name, brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined, image: product.images, sku: product.mpn || undefined, gtin: product.gtin || undefined,
  } : null;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {jsonLd && <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />}

      <section className="grid grid-cols-1 md:grid-cols-5 gap-8 mb-12 animate-fade-in">
        <div className="md:col-span-2">
          <ProductGallery images={product.images || []} name={product.name} />
        </div>
        <div className="md:col-span-3 flex flex-col justify-center">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-sm text-indigo-500 font-medium">{[product.brand, product.category].filter(Boolean).join(" · ")}</span>
            <DataBadge meta={product.meta} />
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold mb-3">{product.name}</h1>
          {product.family_line && (
            <Link href={`/family/${encodeURIComponent(product.family_line)}`} className="inline-flex items-center gap-1 text-sm font-medium text-indigo-500 hover:underline mb-3">Every storage size and store for {product.family_label || "this line"} →</Link>
          )}
          <div className="flex flex-wrap items-center gap-4 mb-4 text-sm text-muted-foreground">
            {product.average_rating ? <span className="flex items-center gap-1"><Star className="w-4 h-4 text-amber-500 fill-current" /><strong className="text-foreground">{product.average_rating}</strong>{product.rating_count ? ` (${product.rating_count.toLocaleString("en-IN")} ratings)` : ""}</span> : null}
            <span>{product.exact_offer_count} exact-match offer{product.exact_offer_count === 1 ? "" : "s"}{product.offer_count > product.exact_offer_count ? ` · ${product.offer_count - product.exact_offer_count} variant/similar` : ""}</span>
            {(product.gtin || product.mpn || product.asin) && <span className="text-xs">ID: {product.gtin || product.mpn || product.asin}</span>}
          </div>
          <ProductHeroPrice initial={product} />

        </div>
      </section>

      <nav className="flex gap-1 overflow-x-auto mb-8 pb-2 border-b border-border/40" aria-label="Sections">
        {[["recommendation", "Recommendation"], ["offers", "Compare offers"], ["history", "Price history"], ["reviews", "What buyers say"], ["trust", "Trust"]].map(([id, label]) => (
          <a key={id} href={`#${id}`} className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 whitespace-nowrap transition-colors">{label}</a>
        ))}
      </nav>

      <ComparisonSections productId={product.id} initialOffers={null} initialRecs={null} trusts={trusts} />

      <PriceHistorySection productId={product.id} initial={null} />

      <section id="reviews" className="mb-16">
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <h2 className="text-2xl font-bold flex items-center gap-2"><MessagesSquare className="w-6 h-6 text-amber-500" /> What buyers say</h2>
          {reviews?.meta && <DataBadge meta={reviews.meta} />}
        </div>
        {reviews?.available ? (
          <div className="glass rounded-2xl p-6">
            <div className="flex flex-wrap items-baseline gap-3 mb-4">
              {reviews.average_rating ? (
                <span className="flex items-center gap-1 text-lg font-bold"><Star className="w-5 h-5 text-amber-500 fill-current" />{reviews.average_rating}</span>
              ) : null}
              <span className="text-sm text-muted-foreground">{reviews.message}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="font-semibold text-sm mb-3 flex items-center gap-2 text-emerald-600"><ThumbsUp className="w-4 h-4" /> What people liked</h3>
                {reviews.positive_themes.length ? (
                  <ul className="space-y-2">
                    {reviews.positive_themes.slice(0, 6).map((t) => (
                      <li key={t.theme} className="text-sm">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="font-medium">{t.theme}</span>
                          <span className="text-xs text-muted-foreground whitespace-nowrap">{t.count.toLocaleString("en-IN")} mentions</span>
                        </div>
                        {t.examples[0] && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">&ldquo;{t.examples[0]}&rdquo;</p>}
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-sm text-muted-foreground">No recurring positives identified.</p>}
              </div>

              <div>
                <h3 className="font-semibold text-sm mb-3 flex items-center gap-2 text-amber-600"><ThumbsDown className="w-4 h-4" /> What people complained about</h3>
                {reviews.negative_themes.length ? (
                  <ul className="space-y-2">
                    {reviews.negative_themes.slice(0, 6).map((t) => (
                      <li key={t.theme} className="text-sm">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="font-medium">{t.theme}</span>
                          <span className="text-xs text-muted-foreground whitespace-nowrap">{t.count.toLocaleString("en-IN")} mentions</span>
                        </div>
                        {t.examples[0] && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">&ldquo;{t.examples[0]}&rdquo;</p>}
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-sm text-muted-foreground">No recurring complaints identified.</p>}
              </div>
            </div>

            {reviews.summary && (
              <div className="mt-6 p-4 rounded-xl bg-muted/30 text-sm">
                <p>{reviews.summary}</p>
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-4">Themes and mention counts are the retailer&apos;s own aggregation over its full review corpus, not a BuyWise summary. A theme appears under complaints when a substantial share of mentions were negative, even if most were positive.</p>
          </div>
        ) : (
          <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">{reviews?.message || "No aggregated review data for this product yet."}</div>
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

      <section id="community" className="mb-16">
        <CommunityReviews productId={product.id} subjectName={product.name} />
      </section>
    </div>
  );
}
