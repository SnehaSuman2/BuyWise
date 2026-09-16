import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CheckCircle, Globe, Store, ArrowLeft, FileText } from "lucide-react";
import { serverGet } from "@/lib/api";
import TrustScoreCard from "@/components/trust/TrustScoreCard";
import CommunityReviews from "@/components/community/CommunityReviews";
import type { Retailer, TrustScoreData } from "@/lib/types";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const r = await serverGet<Retailer>(`/retailers/${id}`);
  return r ? { title: `${r.name} Trust Score`, description: `Is ${r.name} trustworthy? BuyWise Trust Score, risk level and the evidence behind it.`, alternates: { canonical: `/retailer/${id}` } } : { title: "Retailer not found" };
}

export default async function RetailerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [retailer, trust] = await Promise.all([serverGet<Retailer>(`/retailers/${id}`), serverGet<TrustScoreData>(`/retailers/${id}/trust`)]);
  if (!retailer) notFound();
  const policies = (retailer.policies || {}) as Record<string, string | number | boolean>;
  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"><ArrowLeft className="w-4 h-4" /> Back</Link>
      <div className="glass rounded-2xl p-6 mb-6 animate-fade-in">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-muted/50 flex items-center justify-center"><Store className="w-6 h-6 text-muted-foreground" /></div>
          <div className="flex-1">
            <div className="flex items-center gap-2"><h1 className="text-2xl font-bold">{retailer.name}</h1>{retailer.is_curated && <CheckCircle className="w-5 h-5 text-emerald-500" aria-label="Curated retailer" />}</div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground mt-1">
              {retailer.website_url && <a href={retailer.website_url} target="_blank" rel="noopener noreferrer nofollow" className="flex items-center gap-1 hover:text-foreground"><Globe className="w-3 h-3" />{retailer.domain}</a>}
              {retailer.is_marketplace && <span className="flex items-center gap-1"><Store className="w-3 h-3" />Marketplace (third-party sellers)</span>}
              {typeof retailer.total_offers === "number" && <span>{retailer.total_offers} tracked offers</span>}
            </div>
          </div>
        </div>
        {retailer.description && <p className="text-muted-foreground text-sm mt-4">{retailer.description}</p>}
      </div>
      {trust ? <TrustScoreCard trust={trust} showLink={false} /> : <div className="glass rounded-2xl p-6 text-sm text-muted-foreground">Not enough evidence to confidently assess this retailer.</div>}
      {Object.keys(policies).length > 0 && (
        <div className="glass rounded-2xl p-6 mt-6">
          <h2 className="font-semibold mb-3 flex items-center gap-2"><FileText className="w-4 h-4 text-indigo-500" /> Published policies (retailer-stated)</h2>
          <ul className="text-sm space-y-1 text-muted-foreground">
            {"return_window_days" in policies && <li>Return window: {String(policies.return_window_days)} days on eligible items{policies.return_policy_url ? <> · <a href={String(policies.return_policy_url)} target="_blank" rel="noopener noreferrer nofollow" className="text-indigo-500 hover:underline">policy</a></> : null}</li>}
            {policies.buyer_protection && <li>Buyer protection: {String(policies.buyer_protection)}</li>}
            {policies.cod_available && <li>Cash on delivery available</li>}
            {policies.physical_stores && <li>Operates physical stores in India</li>}
            {policies.grievance_officer_published && <li>Publishes a grievance officer contact</li>}
            {policies.verified_on && <li className="text-xs">BuyWise last reviewed these policies on {String(policies.verified_on)}.</li>}
          </ul>
        </div>
      )}
      <div className="mt-6">
        <CommunityReviews retailerId={retailer.id} subjectName={retailer.name} />
      </div>
      {retailer.is_marketplace && <p className="text-xs text-muted-foreground mt-4">On marketplaces the seller of a listing may differ from the platform. BuyWise shows the seller on each offer and assesses seller trust separately when evidence exists.</p>}
    </div>
  );
}
