import { ExternalLink, ShieldCheck } from "lucide-react";
import { formatPrice, getTrustColor, getRecCategoryColor, getRecCategoryLabel, priceStatusLabel } from "@/lib/utils";
import type { Recommendation } from "@/lib/types";
import LockedPanel from "@/components/product/LockedPanel";

export default function RecommendationCards({ recommendations, locked = false }: { recommendations: Recommendation[]; locked?: boolean }) {
  if (locked) return <LockedPanel what="the shopping decision" />;
  if (!recommendations.length) return <p className="text-sm text-muted-foreground">No exact-match offers available to recommend yet.</p>;
  const distinctOffers = new Set(recommendations.map((r) => r.offer_id)).size;
  if (distinctOffers === 1) {
    // Four picks that all point at the same offer is not a decision, it is one offer.
    const rec = recommendations.find((r) => r.category === "BEST_OVERALL") ?? recommendations[0];
    return (
      <div className="glass rounded-2xl p-5 max-w-xl">
        <div className="inline-flex px-3 py-1 rounded-full text-xs font-bold mb-3 border bg-muted/50">Only one offer found</div>
        <div className="text-2xl font-bold mb-0.5 tabular-nums">{formatPrice(rec.price)}</div>
        {!rec.final_price_known && <div className="text-[11px] text-amber-600 mb-1">estimated · may vary at checkout</div>}
        <div className="text-sm text-muted-foreground mb-3">{rec.retailer_name}{rec.seller_name && rec.seller_name !== rec.retailer_name ? ` · ${rec.seller_name}` : ""}</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mb-3 text-xs">
          <span className={`inline-flex items-center gap-1 font-medium ${getTrustColor(rec.trust_score)}`}><ShieldCheck className="w-3 h-3" />Trust {typeof rec.trust_score === "number" ? rec.trust_score : "—"}</span>
          <span className="text-muted-foreground">{rec.match_label}</span>
        </div>
        <p className="text-sm text-muted-foreground">BuyWise has one offer for this product so far, so there is nothing to compare yet. It looks for the same item at other retailers when you open this page, and again as it re-checks prices.</p>
        <a href={rec.go_url} target="_blank" rel="noopener noreferrer sponsored" className="mt-3 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-indigo-500 text-white text-sm font-medium hover:bg-indigo-600 transition-colors">View offer <ExternalLink className="w-3 h-3" /></a>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
      {recommendations.map((rec) => (
        <div key={rec.category} className={`glass rounded-2xl p-5 hover:shadow-lg transition-all duration-300 flex flex-col ${rec.category === "BEST_OVERALL" ? "ring-2 ring-indigo-500/40" : ""}`}>
          <div className={`inline-flex self-start px-3 py-1 rounded-full text-xs font-bold mb-3 border ${getRecCategoryColor(rec.category)}`}>{getRecCategoryLabel(rec.category)}</div>
          <div className="text-2xl font-bold mb-0.5 tabular-nums">{formatPrice(rec.price)}</div>
          {!rec.final_price_known && <div className="text-[11px] text-amber-600 mb-1">estimated · may vary at checkout</div>}
          <div className="text-sm text-muted-foreground mb-3">{rec.retailer_name}{rec.seller_name && rec.seller_name !== rec.retailer_name ? ` · ${rec.seller_name}` : ""}</div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mb-3 text-xs">
            <span className={`inline-flex items-center gap-1 font-medium ${getTrustColor(rec.trust_score)}`}><ShieldCheck className="w-3 h-3" />Trust {typeof rec.trust_score === "number" ? rec.trust_score : "—"}</span>
            <span className="text-muted-foreground">{priceStatusLabel(rec.price_status)}</span>
            <span className="text-muted-foreground">{rec.match_label}</span>
          </div>
          <p className="text-sm text-muted-foreground flex-1">{rec.reason}</p>
          <div className="text-[11px] text-muted-foreground mt-2">Confidence {Math.round(rec.confidence * 100)}%</div>
          <a href={rec.go_url} target="_blank" rel="noopener noreferrer sponsored" className="mt-3 inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-indigo-500 text-white text-sm font-medium hover:bg-indigo-600 transition-colors">View offer <ExternalLink className="w-3 h-3" /></a>
        </div>
      ))}
    </div>
  );
}
