"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle, AlertTriangle, ChevronDown, ChevronUp, ExternalLink, ShieldCheck, Info } from "lucide-react";
import { getTrustColor, riskLabel, formatDate } from "@/lib/utils";
import DataBadge from "@/components/ui/DataBadge";
import type { TrustScoreData, TrustFactor } from "@/lib/types";

function FactorList({ items, tone }: { items: TrustFactor[]; tone: "positive" | "concern" }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">None identified from current evidence.</p>;
  return (
    <ul className="space-y-2">
      {items.map((f) => (
        <li key={f.key} className="text-sm">
          <div className="flex gap-2 items-start">
            {tone === "positive" ? <CheckCircle className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" /> : <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />}
            <div className="flex-1">
              <span className="font-medium">{f.label}</span>
              {typeof f.score === "number" && <span className="text-muted-foreground"> · {f.score}/100 · {f.evidence_count} evidence item{f.evidence_count === 1 ? "" : "s"}</span>}
              {f.examples.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {f.examples.slice(0, 2).map((e, i) => (
                    <li key={i} className="flex gap-1">
                      <span>–</span>
                      <span>{e.claim}{e.url && <a href={e.url} target="_blank" rel="noopener noreferrer nofollow" className="ml-1 text-indigo-500 hover:underline">source</a>}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function TrustScoreCard({ trust, compact = false, showLink = true }: { trust: TrustScoreData; compact?: boolean; showLink?: boolean }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const hasScore = typeof trust.score === "number";
  return (
    <div className="glass rounded-2xl p-6">
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <div className={`text-5xl font-bold ${getTrustColor(trust.score)}`}>{hasScore ? trust.score : "—"}</div>
        <div className="flex-1 min-w-[180px]">
          <div className="font-semibold text-lg flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-500" />
            {showLink && trust.retailer_id ? <Link href={`/retailer/${trust.retailer_id}`} className="hover:text-indigo-500">{trust.subject_name}</Link> : trust.subject_name}
          </div>
          <div className="text-sm text-muted-foreground">BuyWise Trust Score {hasScore ? `${trust.score}/100` : "not available"} · {riskLabel(trust.risk_level)} · Confidence: <span className="capitalize">{trust.confidence_level}</span></div>
        </div>
        <DataBadge meta={trust.meta} />
      </div>
      <p className="text-sm mb-4 flex gap-2"><Info className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />{trust.explanation}</p>
      {!compact && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div><h4 className="font-medium mb-2 text-emerald-500">✓ Factors in favour</h4><FactorList items={trust.factors} tone="positive" /></div>
          <div><h4 className="font-medium mb-2 text-amber-500">⚠ Potential concerns</h4><FactorList items={trust.concerns} tone="concern" /></div>
        </div>
      )}
      {!compact && Object.keys(trust.component_scores || {}).length > 0 && (
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {Object.entries(trust.component_scores).map(([k, v]) => (
            <div key={k} className="p-2 rounded-lg bg-muted/30 text-center">
              <div className={`text-lg font-bold ${getTrustColor(v)}`}>{typeof v === "number" ? v : "—"}</div>
              <div className="text-[11px] text-muted-foreground capitalize">{k.replace(/_/g, " ")}</div>
            </div>
          ))}
        </div>
      )}
      {trust.evidence.length > 0 && (
        <div className="mt-5">
          <button onClick={() => setShowEvidence(!showEvidence)} className="text-sm text-indigo-500 hover:underline flex items-center gap-1">
            {showEvidence ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />} {showEvidence ? "Hide" : "Inspect"} supporting evidence ({trust.evidence_count})
          </button>
          {showEvidence && (
            <ul className="mt-3 space-y-2 max-h-96 overflow-y-auto pr-1">
              {trust.evidence.map((e) => (
                <li key={e.id} className="p-3 rounded-xl bg-muted/30 text-xs">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="px-1.5 py-0.5 rounded bg-background/60 font-medium capitalize">{e.topic.replace(/_/g, " ")}</span>
                    <span className={e.sentiment > 0.15 ? "text-emerald-500" : e.sentiment < -0.15 ? "text-rose-500" : "text-muted-foreground"}>{e.sentiment > 0.15 ? "positive" : e.sentiment < -0.15 ? "negative" : "neutral"}</span>
                    <span className="text-muted-foreground">· {e.source.replace(/_/g, " ")} · confidence {Math.round(e.confidence * 100)}%</span>
                    {e.is_demo && <span className="text-amber-600">· demo</span>}
                    {e.published_at && <span className="text-muted-foreground">· {formatDate(e.published_at)}</span>}
                  </div>
                  <div>{e.extracted_claim || e.title}</div>
                  {e.url && !e.url.includes("example.com") && <a href={e.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-indigo-500 hover:underline mt-1">Open source <ExternalLink className="w-3 h-3" /></a>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className="mt-4 text-[11px] text-muted-foreground">Methodology v{trust.methodology_version} · <Link href="/trust-methodology" className="hover:underline">How Trust Scores work</Link> · Never influenced by payments or affiliate commissions.</p>
    </div>
  );
}
