"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Search, Link2, ArrowRight, ShieldCheck, TrendingDown, Bot, BarChart3, Sparkles, Scale, CheckCircle2, FlaskConical, Radio, Camera } from "lucide-react";
import { downscaleImage, PENDING_PHOTO_KEY } from "@/lib/photo";
import { useMeta } from "@/lib/meta";

const SUGGESTIONS = [
  "Sony WH-1000XM5",
  "iPhone 15 Pro Max 256GB",
  "wireless headphones under ₹25,000",
  "https://www.amazon.in/dp/B09XS7JWHH",
  "MacBook Air M3 15 inch",
  "Samsung Galaxy S24 Ultra 256GB",
];

const FEATURES = [
  { icon: BarChart3, title: "True price comparison", desc: "Product price + shipping − known coupons = the estimated final price, per retailer and seller.", color: "from-indigo-500 to-blue-500" },
  { icon: ShieldCheck, title: "Independent Trust Scores", desc: "0–100 scores built from public evidence, retailer policies and verified experiences — never from payments.", color: "from-emerald-500 to-teal-500" },
  { icon: TrendingDown, title: "Price history & buy/wait", desc: "Real recorded prices only. When there is enough history, BuyWise tells you if it's a good time to buy.", color: "from-purple-500 to-pink-500" },
  { icon: Bot, title: "AI shopping agent", desc: "Ask in plain English. The agent reasons over verified data and never invents prices or reviews.", color: "from-amber-500 to-orange-500" },
];

const STEPS = [
  { title: "Find the exact product", desc: "Search by name or paste a retailer URL. BuyWise matches listings by GTIN, ASIN, model code and variant (storage, colour, size) so you never compare the wrong item." },
  { title: "Compare the true price", desc: "Every offer shows listed price, shipping and known discounts separately. Unknown charges are flagged instead of guessed." },
  { title: "Check who you're buying from", desc: "Retailer and marketplace-seller trust, explained with the evidence behind it." },
  { title: "Decide: buy now or wait", desc: "BEST OVERALL, CHEAPEST, SAFEST, BEST VALUE and FASTEST picks, plus a price-timing signal." },
];

export default function HomePage() {
  const router = useRouter();
  const { meta } = useMeta();
  const [query, setQuery] = useState("");
  const [suggestionIdx, setSuggestionIdx] = useState(0);
  const isUrl = /^https?:\/\//i.test(query);

  useEffect(() => {
    const timer = setInterval(() => setSuggestionIdx((i) => (i + 1) % SUGGESTIONS.length), 3000);
    return () => clearInterval(timer);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    router.push(`/search?q=${encodeURIComponent(query.trim())}`);
  };

  const photoRef = useRef<HTMLInputElement>(null);
  const handlePhoto = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const dataUrl = await downscaleImage(file);
      sessionStorage.setItem(PENDING_PHOTO_KEY, dataUrl);
      router.push("/search");
    } catch {
      router.push("/search?photo=1");
    }
  };

  return (
    <div className="relative">
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 gradient-hero" />
        <div className="absolute top-20 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-10 right-1/4 w-72 h-72 bg-purple-500/10 rounded-full blur-3xl" />
        <div className="relative max-w-4xl mx-auto px-4 pt-20 pb-24 sm:pt-28 sm:pb-32 text-center">
          <div className="animate-fade-in">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 text-indigo-500 text-sm font-medium mb-6"><Sparkles className="w-4 h-4" />AI-Powered Shopping Intelligence</div>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight mb-6">Where should you <span className="bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 bg-clip-text text-transparent">buy</span>?</h1>
            <p className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto mb-10">Compare prices. Check trust. Buy smarter. BuyWise finds the best place to buy — not just the cheapest.</p>
          </div>
          <form onSubmit={handleSubmit} className="animate-slide-up max-w-2xl mx-auto" role="search">
            <div className="relative group">
              <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 rounded-2xl opacity-20 group-hover:opacity-30 blur transition-opacity" />
              <div className="relative glass-strong rounded-2xl p-2">
                <div className="flex items-center gap-2">
                  <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-muted/50">{isUrl ? <Link2 className="w-5 h-5 text-indigo-500" /> : <Search className="w-5 h-5 text-muted-foreground" />}</div>
                  <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Product name, retailer URL, or a photo" className="flex-1 min-w-0 bg-transparent text-lg outline-none placeholder:text-muted-foreground/60" id="search-input" aria-label="Search products" />
                  <input ref={photoRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={handlePhoto} className="hidden" aria-hidden="true" tabIndex={-1} />
                  <button type="button" onClick={() => photoRef.current?.click()} className="p-2.5 rounded-xl hover:bg-muted transition-colors" aria-label="Search by photo" title="Search by photo"><Camera className="w-5 h-5 text-indigo-500" /></button>
                  <button type="submit" className="px-4 sm:px-6 py-2.5 rounded-xl gradient-primary text-white font-medium flex items-center gap-2 hover:shadow-lg hover:shadow-indigo-500/25 transition-all">Search<ArrowRight className="w-4 h-4" /></button>
                </div>
              </div>
            </div>
            <div className="mt-4 h-6 text-sm text-muted-foreground">
              <span>Try: </span>
              <button type="button" onClick={() => setQuery(SUGGESTIONS[suggestionIdx])} className="text-indigo-500 hover:underline animate-fade-in" key={suggestionIdx}>&quot;{SUGGESTIONS[suggestionIdx]}&quot;</button>
            </div>
          </form>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 -mt-8">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map((f, i) => { const Icon = f.icon; return (
            <div key={f.title} className={`glass rounded-2xl p-6 hover:shadow-lg hover:-translate-y-1 transition-all duration-300 animate-slide-up stagger-${i + 1}`} style={{ opacity: 0, animationFillMode: "forwards" }}>
              <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${f.color} flex items-center justify-center mb-4`}><Icon className="w-6 h-6 text-white" /></div>
              <h3 className="font-semibold text-lg mb-2">{f.title}</h3>
              <p className="text-sm text-muted-foreground">{f.desc}</p>
            </div>
          ); })}
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-4 mt-20">
        <h2 className="text-2xl font-bold mb-6 text-center flex items-center justify-center gap-2"><Scale className="w-6 h-6 text-indigo-500" /> How BuyWise decides</h2>
        <ol className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {STEPS.map((s, i) => (
            <li key={s.title} className="glass rounded-2xl p-5 flex gap-4">
              <span className="w-8 h-8 rounded-full gradient-primary text-white font-bold flex items-center justify-center shrink-0">{i + 1}</span>
              <div><h3 className="font-semibold mb-1">{s.title}</h3><p className="text-sm text-muted-foreground">{s.desc}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="max-w-4xl mx-auto px-4 mt-16">
        <div className="glass rounded-2xl p-6">
          <h2 className="font-semibold mb-3 flex items-center gap-2"><CheckCircle2 className="w-5 h-5 text-emerald-500" /> Our principles</h2>
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm text-muted-foreground">
            <li>• No fabricated prices, reviews or price history</li>
            <li>• Trust Scores cannot be bought or influenced by affiliate commissions</li>
            <li>• Unknown shipping or coupons are marked unknown, not assumed</li>
            <li>• Similar products are never presented as the same product</li>
            <li>• Every score comes with the evidence behind it</li>
            <li>• Demo data is always labelled as demo data</li>
          </ul>
          {meta && (
            <p className="mt-4 text-xs flex items-center gap-2">
              {meta.demo_mode ? <FlaskConical className="w-3.5 h-3.5 text-amber-500" /> : <Radio className="w-3.5 h-3.5 text-emerald-500" />}
              <span className="text-muted-foreground">Data status: <strong className={meta.demo_mode ? "text-amber-600" : "text-emerald-600"}>{meta.demo_mode ? "DEMO MODE — simulated data" : "LIVE DATA"}</strong>{meta.ai_mode === "demo" ? " · AI explanations in demo mode" : " · AI explanations live"}</span>
            </p>
          )}
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-4 mt-20 text-center">
        <h2 className="text-3xl font-bold mb-4">Ready to shop smarter?</h2>
        <p className="text-muted-foreground mb-8">Search by name, paste a product URL, or <Link href="/agent" className="text-indigo-500 hover:underline">ask the AI agent</Link>.</p>
        <button onClick={() => document.getElementById("search-input")?.focus()} className="px-8 py-3 rounded-xl gradient-primary text-white font-medium text-lg hover:shadow-lg hover:shadow-indigo-500/25 transition-all">Start searching</button>
      </section>
    </div>
  );
}
