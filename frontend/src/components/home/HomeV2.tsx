"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight, Bell, Camera, Check, ChevronDown, Headphones, Laptop, Link2, LoaderCircle, Search, ShieldCheck, Smartphone, Sparkles, Truck } from "lucide-react";
import { downscaleImage, PENDING_PHOTO_KEY } from "@/lib/photo";
import { track } from "@/lib/analytics";

const categories = [
  { name: "Headphones", query: "Sony WH-1000XM5", icon: Headphones, note: "Find your next favourite sound", color: "peach" },
  { name: "Smartphones", query: "Samsung Galaxy S24 256GB", icon: Smartphone, note: "The right phone. A better deal.", color: "lavender" },
  { name: "Laptops", query: "MacBook Air M3", icon: Laptop, note: "More possibilities, less searching", color: "mint" },
];
const faqs = [
  ["What does BuyWise Pro unlock?", "Preview selected retailer offers on product pages when available. Pro unlocks the full comparison, best-overall and safest picks, recorded price history, and buy/wait guidance when enough observations exist."],
  ["Can I buy directly on BuyWise?", "BuyWise helps you compare. When you choose an offer, you visit the retailer to complete your purchase. Always confirm the final price, delivery and return policy at checkout."],
  ["What does the Trust Score mean?", "It is BuyWise’s assessment of public evidence and retailer policies, not a guarantee. Open the score on a product page to see the reasons and any concerns before deciding."],
  ["Are these prices always live?", "Availability and prices can change. Results show their data status, and demo results are clearly labelled. Unknown delivery charges are flagged, and price history only includes observations we have actually recorded."],
];
export default function HomeV2() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"name" | "link">("name");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const photo = useRef<HTMLInputElement>(null);
  const input = useRef<HTMLInputElement>(null);
  function search(value: string, source: string) {
    const trimmed = value.trim();
    if (!trimmed) { setError("Enter a product name to get started, or try an example below."); input.current?.focus(); return; }
    if (mode === "link" && source === "form" && !/^https?:\/\/[^\s]+$/i.test(trimmed)) { setError("Paste a full product link starting with https://."); return; }
    track("search_started", { query_type: /^https?:\/\//i.test(trimmed) ? "url" : "text", source });
    router.push(`/search?q=${encodeURIComponent(trimmed)}`);
  }
  async function choosePhoto(file?: File) {
    if (!file) return;
    setError(""); setBusy(true);
    try {
      if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 20 * 1024 * 1024) throw new Error("Choose a JPG, PNG or WebP image smaller than 20 MB.");
      sessionStorage.setItem(PENDING_PHOTO_KEY, await downscaleImage(file));
      track("search_started", { query_type: "image", source: "home" });
      router.push("/search");
    } catch (e) { setError(e instanceof Error ? e.message : "We couldn’t read that photo. Try another image or search by name."); }
    finally { setBusy(false); }
  }
  return <div className="v2-home">
    <section className="v2-hero"><div className="v2-container v2-hero-grid"><div>
      <div className="v2-eyebrow"><Sparkles size={16} aria-hidden="true" /> AI-powered shopping comparison platform</div>
      <h1>Love the product.<br /><span>Feel good about<br className="hidden xl:block" /> the price.</span></h1>
      <p className="v2-intro">BuyWise brings retailer offers, seller trust and price insights together, with AI to help explain your options. Search a product to get started.</p>
      <form className="v2-search" role="search" onSubmit={(e) => { e.preventDefault(); search(query, "form"); }}>
        <div className="v2-search-modes" aria-label="Search method">
          <button type="button" aria-pressed={mode === "name"} onClick={() => { setMode("name"); setError(""); input.current?.focus(); }}><Search size={16} /> Product name</button>
          <button type="button" aria-pressed={mode === "link"} onClick={() => { setMode("link"); setError(""); input.current?.focus(); }}><Link2 size={16} /> Paste a link</button>
          <button type="button" disabled={busy} onClick={() => photo.current?.click()}>{busy ? <LoaderCircle size={16} className="animate-spin" /> : <Camera size={16} />} Photo</button>
        </div>
        <label htmlFor="v2-query" className="sr-only">{mode === "name" ? "Product name or model" : "Product link"}</label>
        <div className="v2-search-input"><Search size={22} aria-hidden="true" /><input ref={input} id="v2-query" value={query} onChange={(e) => { setQuery(e.target.value); setError(""); }} placeholder={mode === "name" ? "What’s on your wishlist?" : "https://www.amazon.in/…"} aria-describedby="v2-search-help" aria-invalid={Boolean(error)} /><button className="v2-button" type="submit">Compare <ArrowRight size={18} /></button></div>
        <input ref={photo} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => { void choosePhoto(e.target.files?.[0]); e.target.value = ""; }} />
        <p id="v2-search-help" className="v2-search-help">{mode === "name" ? "Add a model or storage size for a closer match." : "Copy a product page link from your retailer."} Preview selected offers. Unlock top picks, all retailers and price history with Pro.</p>
        {error && <p className="v2-form-error" role="alert">{error}</p>}
      </form>
      <div className="v2-examples"><span>Try a search</span>{["Sony WH-1000XM5", "iPhone 15 128GB"].map(q => <button key={q} onClick={() => search(q, "example")}>{q} <ArrowUpRight size={13} /></button>)}</div>
      <a href="#how-it-works" className="v2-how-link">New here? See how it works <ChevronDown size={15} /></a>
    </div><div className="v2-preview" aria-label="Illustrative comparison preview, not live offers">
      <div className="v2-preview-top"><span><Sparkles size={15} /> A clearer picture before you buy</span><span className="v2-example-label">Illustration</span></div>
      <div className="v2-product-art"><Headphones strokeWidth={1} aria-hidden="true" /><div className="v2-art-tag"><ShieldCheck size={17} /> Look beyond the price</div></div>
      <div className="v2-preview-body"><p className="v2-small-label">YOUR NEXT PAIR OF HEADPHONES</p><h2>Same product. All the details.</h2><p className="v2-preview-description">See what matters, side by side.</p>
        {[{ icon: Check, title: "The right match", text: "Model, colour and variant checked" }, { icon: Truck, title: "The fuller price", text: "Item + known shipping − known discounts" }, { icon: ShieldCheck, title: "The reasons to trust", text: "Seller evidence, with concerns explained" }].map(({ icon: Icon, title, text }) => <div className="v2-preview-row" key={title}><span><Icon size={19} /></span><div><strong>{title}</strong><p>{text}</p></div><Check size={16} className="v2-row-check" /></div>)}
        <div className="v2-preview-note"><Bell size={17} /><span>Not ready? Save it and set a price alert.</span></div>
      </div>
    </div></div></section>
    <div className="v2-principles"><div className="v2-container"><span><ShieldCheck size={18} /> Independent trust assessments</span><span><Check size={18} /> Unknown charges clearly marked</span><span><Bell size={18} /> Your wishlist, on your terms</span></div></div>
    <section className="v2-container v2-section" id="how-it-works"><div className="v2-section-heading"><div><p className="v2-small-label">LESS GUESSWORK. MORE CONFIDENCE.</p><h2>From “I want it” to “I found it.”</h2></div><p>Three simple steps.<br />You’re in control the whole way.</p></div>
      <ol className="v2-steps">{[{ title: "Find your product", text: "Type a name, paste a link, or upload a photo. Check the model and variant in your results.", icon: Search }, { title: "Compare what matters", text: "Explore offers, known costs and seller evidence. See which details are still unknown.", icon: ShieldCheck }, { title: "Buy now. Or keep an eye on it.", text: "Continue to the retailer, or create an account to save the product and set a price alert.", icon: Bell }].map(({ title, text, icon: Icon }, i) => <li key={title}><div className="v2-step-top"><span>0{i + 1}</span><Icon size={23} /></div><h3>{title}</h3><p>{text}</p></li>)}</ol>
    </section>
    <section className="v2-container v2-section v2-categories"><div className="v2-section-heading"><div><p className="v2-small-label">A GOOD PLACE TO START</p><h2>What are you shopping for?</h2></div><Link href="/agent">Help me choose <ArrowUpRight size={17} /></Link></div><div className="v2-category-grid">{categories.map(({ name, query: q, icon: Icon, note, color }) => <button key={name} className={`v2-category ${color}`} onClick={() => search(q, "category")}><div><h3>{name}</h3><p>{note}</p><span>Explore a product <ArrowRight size={16} /></span></div><Icon strokeWidth={1.2} className="v2-category-icon" /></button>)}</div></section>
    <section className="v2-container v2-section"><div className="v2-assistant"><div className="v2-assistant-symbol"><Sparkles size={34} /></div><div><p className="v2-small-label">A LITTLE HELP GOES A LONG WAY</p><h2>Know your budget, but not your product?</h2><p>Tell the shopping assistant what you need. Start with “headphones under ₹5,000”.</p></div><Link href="/agent" className="v2-button">Help me find it <ArrowRight size={18} /></Link></div></section>
    <section className="v2-container v2-section v2-faq"><div><p className="v2-small-label">GOOD QUESTIONS</p><h2>A little clarity<br />before you start.</h2><Link href="/trust-methodology">How we assess trust <ArrowUpRight size={16} /></Link></div><div>{faqs.map(([q, a]) => <details key={q} onToggle={(e) => { if (e.currentTarget.open) track("help_opened", { topic: q }); }}><summary>{q}<ChevronDown size={18} /></summary><p>{a}</p></details>)}</div></section>
  </div>;
}
