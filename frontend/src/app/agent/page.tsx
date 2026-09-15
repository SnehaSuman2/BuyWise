"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { Send, Bot, User, Sparkles, Loader2, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatPrice, getTrustColor, priceActionLabel, getPriceActionColor } from "@/lib/utils";
import SafeText from "@/components/ui/SafeText";
import DataBadge from "@/components/ui/DataBadge";
import type { AgentResponse } from "@/lib/types";

interface Message { id: string; role: "user" | "agent"; content: string; response?: AgentResponse; error?: boolean }

const SUGGESTIONS = [
  "Best wireless headphones under ₹25,000",
  "Which phone is best for photography under ₹70,000?",
  "MacBook Air M3 vs Dell XPS 15",
  "Is Flipkart trustworthy?",
  "Should I buy the Sony WH-1000XM5 now?",
  "Where should I buy the iPhone 15 Pro Max 256GB?",
];

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([{ id: "welcome", role: "agent", content: "Hi! I'm the BuyWise shopping agent. Ask me where to buy something, whether a retailer is trustworthy, or if now is a good time to buy. I only use verified data — if I don't have it, I'll say so." }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const send = async (text?: string) => {
    const query = (text ?? input).trim();
    if (!query || loading) return;
    setInput("");
    setMessages((m) => [...m, { id: `${Date.now()}-u`, role: "user", content: query }]);
    setLoading(true);
    try {
      const res = await api.agent(query);
      setMessages((m) => [...m, { id: `${Date.now()}-a`, role: "agent", content: res.answer, response: res }]);
    } catch (e) {
      setMessages((m) => [...m, { id: `${Date.now()}-e`, role: "agent", content: (e as ApiError).message || "Something went wrong.", error: true }]);
    } finally { setLoading(false); }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 flex flex-col" style={{ minHeight: "calc(100vh - 8rem)" }}>
      <div className="text-center mb-6">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 text-indigo-500 text-sm font-medium mb-3"><Bot className="w-4 h-4" /> AI Shopping Agent</div>
        <h1 className="text-2xl font-bold">Ask me anything about shopping</h1>
        <p className="text-sm text-muted-foreground mt-1">Answers are grounded in BuyWise search, true-price, trust and price-history data.</p>
      </div>

      <div className="flex-1 space-y-4 mb-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 animate-slide-up ${msg.role === "user" ? "justify-end" : ""}`}>
            {msg.role === "agent" && <div className="w-8 h-8 rounded-full gradient-primary flex items-center justify-center shrink-0 mt-1"><Sparkles className="w-4 h-4 text-white" /></div>}
            <div className={`max-w-[85%] ${msg.role === "user" ? "bg-indigo-500 text-white rounded-2xl rounded-tr-md px-4 py-3" : `glass rounded-2xl rounded-tl-md px-4 py-3 ${msg.error ? "border border-rose-500/30" : ""}`}`}>
              <SafeText text={msg.content} className="text-sm" />
              {msg.response && (
                <div className="mt-3 space-y-3">
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <DataBadge meta={msg.response.meta} />
                    <span>intent: {msg.response.intent.kind.replace(/_/g, " ")}</span>
                    {msg.response.intent.budget_max ? <span>budget ≤ {formatPrice(msg.response.intent.budget_max)}</span> : null}
                    <span>AI: {msg.response.ai_provider}</span>
                  </div>
                  {msg.response.meta.warnings.map((w) => <p key={w} className="text-xs text-amber-600">{w}</p>)}
                  {msg.response.trust && (
                    <div className="p-3 rounded-xl bg-background/50 text-sm">
                      <div className="flex items-center gap-2 font-medium"><ShieldCheck className="w-4 h-4 text-indigo-500" />{msg.response.trust.subject_name}: <span className={getTrustColor(msg.response.trust.score)}>{msg.response.trust.score ?? "—"}/100</span><span className="text-muted-foreground font-normal">· {msg.response.trust.risk_level} risk · {msg.response.trust.confidence_level} confidence</span></div>
                      {msg.response.trust.retailer_id && <Link href={`/retailer/${msg.response.trust.retailer_id}`} className="text-xs text-indigo-500 hover:underline">See evidence →</Link>}
                    </div>
                  )}
                  {msg.response.price_signal && (
                    <div className="p-3 rounded-xl bg-background/50 text-sm"><span className={`font-semibold ${getPriceActionColor(msg.response.price_signal.action)}`}>{priceActionLabel(msg.response.price_signal.action)}</span> — {msg.response.price_signal.reasoning}</div>
                  )}
                  {msg.response.products.map(({ product, recommendations }) => {
                    const best = recommendations?.recommendations.find((r) => r.category === "BEST_OVERALL");
                    const cheapest = recommendations?.recommendations.find((r) => r.category === "CHEAPEST");
                    return (
                      <Link key={product.id} href={`/product/${product.id}`} className="flex items-center gap-3 p-2 rounded-xl bg-background/50 hover:bg-background/80 transition-colors">
                                                <img src={product.image || "https://placehold.co/80x80/1a1a2e/e0e0e0?text=?"} alt="" className="w-14 h-14 rounded-lg object-cover" />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{product.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {best ? <>Best overall: {best.retailer_name} {formatPrice(best.price)} · trust <span className={getTrustColor(best.trust_score)}>{best.trust_score ?? "—"}</span></> : product.lowest_price ? `from ${formatPrice(product.lowest_price)}` : "no price"}
                            {cheapest && best && cheapest.offer_id !== best.offer_id ? ` · cheapest ${cheapest.retailer_name} ${formatPrice(cheapest.price)}` : ""}
                          </div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
            {msg.role === "user" && <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center shrink-0 mt-1"><User className="w-4 h-4" /></div>}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3 animate-fade-in"><div className="w-8 h-8 rounded-full gradient-primary flex items-center justify-center shrink-0"><Sparkles className="w-4 h-4 text-white" /></div><div className="glass rounded-2xl rounded-tl-md px-4 py-3 text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Searching retailers, checking prices and trust…</div></div>
        )}
        <div ref={endRef} />
      </div>

      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 mb-4">{SUGGESTIONS.map((s) => <button key={s} onClick={() => send(s)} className="px-3 py-1.5 rounded-full text-xs font-medium glass hover:bg-muted/50 transition-colors">{s}</button>)}</div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2 sticky bottom-4">
        <input type="text" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Describe what you're looking for…" className="flex-1 min-w-0 px-4 py-3 rounded-xl glass-strong text-sm outline-none focus:ring-2 focus:ring-indigo-500/30" disabled={loading} aria-label="Message" maxLength={500} />
        <button type="submit" disabled={loading || !input.trim()} className="px-4 py-3 rounded-xl gradient-primary text-white disabled:opacity-50 transition-opacity" aria-label="Send"><Send className="w-5 h-5" /></button>
      </form>
    </div>
  );
}
