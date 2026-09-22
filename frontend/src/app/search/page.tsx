"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Star, Search, Link2, AlertTriangle, Camera, X, Lock } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatPrice, matchBadgeClass } from "@/lib/utils";
import DataBadge from "@/components/ui/DataBadge";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { ProductSearchResult, SearchResponse } from "@/lib/types";
import { downscaleImage, PENDING_PHOTO_KEY } from "@/lib/photo";
import { track } from "@/lib/analytics";

function ProductCard({ product, visual = false }: { product: ProductSearchResult; visual?: boolean }) {
  return (
    <Link href={`/product/${product.id}`} className="glass rounded-2xl overflow-hidden hover:shadow-xl hover:-translate-y-1 transition-all duration-300 group flex flex-col">
      <div className="aspect-square bg-muted/30 relative overflow-hidden">
                <img src={product.image || "https://placehold.co/400x400/1a1a2e/e0e0e0?text=No+image"} alt={product.name} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
        {!product.locked && product.offer_count > 0 && <div className="absolute top-3 right-3 px-2 py-1 rounded-lg bg-indigo-500 text-white text-xs font-medium">{product.offer_count} offer{product.offer_count === 1 ? "" : "s"}</div>}
        {product.is_demo && <div className="absolute top-3 left-3 px-2 py-0.5 rounded-md bg-amber-500 text-white text-[10px] font-bold uppercase">Demo</div>}
      </div>
      <div className="p-4 flex flex-col flex-1">
        <div className="text-xs text-indigo-500 font-medium mb-1">{[product.brand, product.category].filter(Boolean).join(" · ")}</div>
        <h3 className="font-semibold text-sm leading-snug mb-2 line-clamp-2 group-hover:text-indigo-500 transition-colors">{product.name}</h3>
        {product.match && <span className={`self-start mb-2 px-2 py-0.5 rounded-md border text-[11px] font-medium ${matchBadgeClass(product.match.match_type)}`}>{visual ? "Visual match" : product.match.label} · {Math.round(product.match.confidence * 100)}%</span>}
        <div className="flex items-end justify-between mt-auto">
          <div>
            {product.locked ? (
              <div className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-500"><Lock className="w-3.5 h-3.5" /> {product.hint || "Price with Pro"}</div>
            ) : (
              <>
                <div className="text-lg font-bold">{product.lowest_price ? formatPrice(product.lowest_price) : "No price"}</div>
                {product.highest_price && product.lowest_price && product.highest_price > product.lowest_price && <div className="text-xs text-muted-foreground">up to {formatPrice(product.highest_price)}</div>}
              </>
            )}
          </div>
          {product.average_rating ? <div className="flex items-center gap-1 text-sm text-amber-500"><Star className="w-4 h-4 fill-current" />{product.average_rating}</div> : null}
        </div>
        {!product.locked && product.retailers.length > 0 && <div className="text-[11px] text-muted-foreground mt-2 truncate">{product.retailers.join(", ")}</div>}
      </div>
    </Link>
  );
}

const SORTS: { key: string; label: string }[] = [{ key: "relevance", label: "Relevance" }, { key: "price_asc", label: "Price: low" }, { key: "price_desc", label: "Price: high" }, { key: "rating", label: "Rating" }];

function SearchContent() {
  const params = useSearchParams();
  const router = useRouter();
  const q = params.get("q") || "";
  const sort = params.get("sort") || "relevance";
  const wantsPhoto = params.get("photo") === "1";
  const [data, setData] = useState<SearchResponse | null>(null);
  const [photoData, setPhotoData] = useState<SearchResponse | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState(q);
  const [showAllWarnings, setShowAllWarnings] = useState(false);
  const [prevQ, setPrevQ] = useState(q);
  const fileRef = useRef<HTMLInputElement>(null);
  if (prevQ !== q) { setPrevQ(q); setInput(q); }
  const isUrl = /^https?:\/\//i.test(q);
  const photoMode = !q && photoPreview !== null;
  const shown = q ? data : photoMode ? photoData : null;

  useEffect(() => {
    if (!q) return;
    let cancelled = false;
    (async () => {
      setLoading(true); setError(null);
      try {
        const res = await api.search(isUrl ? { url: q, sort_by: sort, page_size: 24 } : { query: q, sort_by: sort, page_size: 24 });
        if (!cancelled) setData(res);
        if (!cancelled) track("search", { query_type: res.query_type, search_term: isUrl ? undefined : q, results: res.total_results, data_mode: res.meta.data_mode });
      } catch (e) {
        if (!cancelled) setError((e as ApiError).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [q, sort, isUrl]);

  const runPhotoSearch = async (dataUrl: string) => {
    setPhotoPreview(dataUrl);
    setPhotoData(null);
    setLoading(true); setError(null);
    try {
      const res = await api.search({ image_base64: dataUrl, page_size: 24 });
      setPhotoData(res);
      track("search", { query_type: "image", results: res.total_results, data_mode: res.meta.data_mode });
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  // A photo chosen on the home page arrives through session storage. State is only
  // touched from promise callbacks, never synchronously inside the effect.
  useEffect(() => {
    if (q) return;
    let pending: string | null = null;
    try { pending = sessionStorage.getItem(PENDING_PHOTO_KEY); sessionStorage.removeItem(PENDING_PHOTO_KEY); } catch { pending = null; }
    if (!pending) return;
    const dataUrl = pending;
    let live = true;
    Promise.resolve().then(() => { if (live) { setPhotoPreview(dataUrl); setPhotoData(null); setError(null); setLoading(true); } });
    api.search({ image_base64: dataUrl, page_size: 24 })
      .then((res) => { if (live) setPhotoData(res); })
      .catch((e: ApiError) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [q]);

  const onPhotoChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) { setError("Please choose a JPEG, PNG or WebP image."); return; }
    try {
      const dataUrl = await downscaleImage(file);
      if (q) router.push("/search");
      await runPhotoSearch(dataUrl);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const clearPhoto = () => { setPhotoPreview(null); setPhotoData(null); setError(null); };

  const submit = (e: React.FormEvent) => { e.preventDefault(); if (input.trim()) { clearPhoto(); router.push(`/search?q=${encodeURIComponent(input.trim())}`); } };

  const heading = q
    ? (isUrl ? "Matches for your link" : <>Results for &quot;{q}&quot;</>)
    : photoMode ? "Matches for your photo" : "Search";

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <form onSubmit={submit} className="glass rounded-2xl p-2 flex items-center gap-2 mb-6 max-w-2xl" role="search">
        <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-muted/50">{/^https?:\/\//i.test(input) ? <Link2 className="w-5 h-5 text-indigo-500" /> : <Search className="w-5 h-5 text-muted-foreground" />}</div>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Search products or paste a retailer URL" className="flex-1 min-w-0 bg-transparent outline-none" aria-label="Search" />
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={onPhotoChosen} className="hidden" aria-hidden="true" tabIndex={-1} />
        <button type="button" onClick={() => fileRef.current?.click()} className="p-2 rounded-xl hover:bg-muted transition-colors" aria-label="Search by photo" title="Search by photo">
          <Camera className="w-5 h-5 text-indigo-500" />
        </button>
        <button type="submit" className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">Search</button>
      </form>

      {wantsPhoto && !photoPreview && !q && (
        <div className="glass rounded-2xl p-6 mb-6 max-w-2xl">
          <h2 className="font-semibold mb-1 flex items-center gap-2"><Camera className="w-4 h-4 text-indigo-500" /> Search by photo</h2>
          <p className="text-sm text-muted-foreground mb-4">Take a picture of a product, or a screenshot of a listing, and BuyWise will look for it across Indian retailers. The photo is resized on your device before upload.</p>
          <button type="button" onClick={() => fileRef.current?.click()} className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium">Choose a photo</button>
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{heading}</h1>
        {shown && <DataBadge meta={shown.meta} />}
      </div>
      {photoMode && photoPreview && (
        <div className="flex items-center gap-3 mb-4">
          <img src={photoPreview} alt="Your photo" className="w-16 h-16 rounded-xl object-cover border border-border/40" />
          <p className="text-sm text-muted-foreground flex-1">Visual look-alikes{shown?.query && shown.query !== "image search" ? <>, identified as &ldquo;{shown.query}&rdquo;</> : null}. Check the product name and seller on each card before comparing prices.</p>
          <button type="button" onClick={clearPhoto} className="p-2 rounded-lg hover:bg-muted" aria-label="Clear photo"><X className="w-4 h-4" /></button>
        </div>
      )}
      {shown?.query_type === "url" && (
        <p className="text-sm text-muted-foreground mb-4">Detected retailer: <strong>{shown.detected_retailer || "unknown"}</strong> · identified as &quot;{shown.query}&quot;. Each result shows how confidently it matches the product in your link.</p>
      )}
      {shown && shown.meta.warnings.length > 0 && (
        <div className="mb-4">
          {(showAllWarnings ? shown.meta.warnings : shown.meta.warnings.slice(0, 1)).map((w) => (
            <p key={w} className="text-sm text-amber-600 flex items-start gap-2 mb-1"><AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />{w}</p>
          ))}
          {shown.meta.warnings.length > 1 && (
            <button type="button" onClick={() => setShowAllWarnings((v) => !v)} className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2">
              {showAllWarnings ? "Show less" : `${shown.meta.warnings.length - 1} more note${shown.meta.warnings.length - 1 === 1 ? "" : "s"} about what was filtered`}
            </button>
          )}
        </div>
      )}

      {q && (
        <div className="flex items-center gap-2 mb-6 flex-wrap">
          {SORTS.map((s) => <button key={s.key} onClick={() => router.push(`/search?q=${encodeURIComponent(q)}&sort=${s.key}`)} className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${sort === s.key ? "bg-indigo-500/10 text-indigo-500" : "bg-muted/50 hover:bg-muted"}`}>{s.label}</button>)}
          {shown && <span className="text-sm text-muted-foreground ml-auto">{shown.total_results} product{shown.total_results === 1 ? "" : "s"}</span>}
        </div>
      )}

      {loading && <Spinner label={photoMode ? "Looking for this product…" : "Searching retailers…"} className="py-10 justify-center" />}
      {error && <ErrorBox message={error} />}
      {!loading && !error && shown && shown.results.length === 0 && (
        <div className="text-center py-20"><p className="text-lg text-muted-foreground">No products found{q ? <> for &quot;{q}&quot;</> : " for this photo"}</p><p className="text-sm text-muted-foreground mt-2">{q ? "Try a more specific product name, model number or a retailer URL." : "Try a clearer photo of the product or its box, or type the product name."}</p></div>
      )}
      {!loading && shown && shown.results.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {shown.results.map((product, i) => (
            <div key={product.id} className="animate-slide-up" style={{ animationDelay: `${Math.min(i, 12) * 0.04}s`, opacity: 0, animationFillMode: "forwards" }}><ProductCard product={product} visual={shown.query_type === "image"} /></div>
          ))}
        </div>
      )}
      {!q && !photoMode && !wantsPhoto && <p className="text-muted-foreground text-sm">Type a product name, paste a link from Amazon, Flipkart, Croma and other Indian retailers, or use the camera to search by photo.</p>}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="max-w-7xl mx-auto px-4 py-8"><div className="animate-shimmer h-96 rounded-2xl" /></div>}>
      <SearchContent />
    </Suspense>
  );
}
