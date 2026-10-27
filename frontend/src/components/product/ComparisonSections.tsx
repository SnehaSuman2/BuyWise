"use client";

import { useEffect, useState } from "react";
import { Award, IndianRupee, Info, Shield, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPrice, getPriceActionColor, getTrustColor, priceStatusLabel, riskLabel } from "@/lib/utils";
import DataBadge from "@/components/ui/DataBadge";
import SafeText from "@/components/ui/SafeText";
import OffersTable from "@/components/product/OffersTable";
import RecommendationCards from "@/components/product/RecommendationCards";
import LockedPanel from "@/components/product/LockedPanel";
import { usePriceHistory } from "@/lib/usePriceHistory";
import type { OfferComparison, RecommendationSet, TrustScoreData } from "@/lib/types";

/** Fetch for guests and subscribers; discard snapshots when the viewer changes. */
export default function ComparisonSections({
  productId,
  initialOffers,
  initialRecs,
  trusts,
}: {
  productId: string;
  initialOffers: OfferComparison | null;
  initialRecs: RecommendationSet | null;
  trusts: TrustScoreData[] | null;
}) {
  const { user, loading: authLoading } = useAuth();
  const viewer = `${user?.id ?? "anon"}:${user?.plan ?? "none"}:${user?.role ?? "none"}:${productId}`;
  const [snapshot, setSnapshot] = useState<{ viewer: string; offers: OfferComparison | null; recs: RecommendationSet | null } | null>(null);
  const { history } = usePriceHistory(productId, 90);
  const offers = snapshot?.viewer === viewer ? snapshot.offers : initialOffers;
  const recs = snapshot?.viewer === viewer ? snapshot.recs : initialRecs;
  const loading = authLoading || snapshot?.viewer !== viewer;

  useEffect(() => {
    if (authLoading) return;
    let live = true;
    Promise.all([api.offers(productId).catch(() => null), api.recommendations(productId).catch(() => null)])
      .then(([offers, recs]) => { if (live) setSnapshot({ viewer, offers, recs }); });
    return () => { live = false; };
  }, [authLoading, viewer, productId]);

  const best = recs?.recommendations.find((r) => r.category === "BEST_OVERALL") ?? null;
  const bestTrust = best ? trusts?.find((t) => t.retailer_id === best.retailer_id) ?? null : null;
  const signal = history?.signal ?? null;
  const locked = Boolean(offers?.locked || recs?.locked);

  return (
    <>
      {best && (
        <div className="glass rounded-2xl p-4 mb-10 grid grid-cols-1 sm:grid-cols-3 gap-4">
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
            <div className="text-xs text-muted-foreground">{history?.stats && history.stats.observations >= 2 && history.stats.percent_vs_average != null ? `${Math.abs(history.stats.percent_vs_average)}% ${history.stats.percent_vs_average < 0 ? "below" : "above"} 90-day avg` : history?.history?.[0] ? `Tracking since ${new Date(history.history[0].date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}` : "Not enough BuyWise history yet"}</div>
          </div>
        </div>
      )}

      <section id="recommendation" className="mb-16">
        <div className="flex flex-wrap items-center gap-3 mb-6"><h2 className="text-2xl font-bold flex items-center gap-2"><Award className="w-6 h-6 text-indigo-500" /> Shopping decision</h2>{recs && !recs.locked && <DataBadge meta={recs.meta} />}</div>
        {loading && !recs ? <div role="status" aria-label="Loading shopping insights" className="animate-shimmer h-48 rounded-2xl" /> : recs ? <RecommendationCards recommendations={recs.recommendations} locked={Boolean(recs.locked)} /> : <p className="text-sm text-muted-foreground">Recommendations unavailable right now.</p>}
        {recs?.ai_explanation && !recs.locked && (
          <div className="glass rounded-2xl p-5 mt-6">
            <div className="flex items-center gap-2 text-sm font-semibold mb-2"><Sparkles className="w-4 h-4 text-indigo-500" /> AI recommendation <span className="text-xs font-normal text-muted-foreground">({recs.ai_provider === "demo" ? "template explanation — AI provider not configured" : `explained by ${recs.ai_provider}, grounded in the data above`})</span></div>
            <SafeText text={recs.ai_explanation} className="text-sm" />
          </div>
        )}
      </section>

      <section id="offers" className="mb-16">
        <div className="flex flex-wrap items-center gap-3 mb-6"><h2 className="text-2xl font-bold flex items-center gap-2"><IndianRupee className="w-6 h-6 text-emerald-500" /> Compare offers</h2>{offers && <DataBadge meta={offers.meta} />}</div>
        {offers?.meta.warnings.map((w) => <p key={w} className="text-sm text-amber-600 mb-2 flex gap-2"><Info className="w-4 h-4 mt-0.5" />{w}</p>)}
        {loading && !offers ? <div role="status" aria-label="Loading retailer comparison" className="animate-shimmer h-48 rounded-2xl" /> : (
          <div className="glass rounded-2xl overflow-hidden">
            {offers ? <OffersTable comparison={offers} /> : <p className="p-6 text-sm text-muted-foreground">Offers temporarily unavailable.</p>}
          </div>
        )}
        {!offers && locked && <div className="mt-4"><LockedPanel /></div>}
      </section>
    </>
  );
}
