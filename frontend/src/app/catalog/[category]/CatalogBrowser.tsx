"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock, SlidersHorizontal, Store, BadgeCheck, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { specSummary, storageLabel } from "@/lib/specs";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { CatalogPage, CatalogModelCard } from "@/lib/types";

const SCREEN_BANDS: { key: string; label: string; min?: number; max?: number }[] = [
  { key: "compact", label: "Up to 6.3\"", max: 6.3 },
  { key: "standard", label: "6.3\" to 6.7\"", min: 6.3, max: 6.7 },
  { key: "large", label: "6.7\" and up", min: 6.7 },
];
const PRICE_BANDS: { key: string; label: string; min?: number; max?: number }[] = [
  { key: "u20", label: "Under ₹20,000", max: 20000 },
  { key: "20-40", label: "₹20,000 to ₹40,000", min: 20000, max: 40000 },
  { key: "40-80", label: "₹40,000 to ₹80,000", min: 40000, max: 80000 },
  { key: "80p", label: "₹80,000 and up", min: 80000 },
];
const SORTS = [["newest", "Newest"], ["price_asc", "Price: low"], ["price_desc", "Price: high"], ["name", "Name"]] as const;

function Chip({ active, onClick, children, title }: { active: boolean; onClick: () => void; children: React.ReactNode; title?: string }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={active} className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${active ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40 hover:bg-muted/50"}`}>{children}</button>
  );
}

function ModelCard({ m }: { m: CatalogModelCard }) {
  return (
    <Link href={`/family/${encodeURIComponent(m.line)}`} className="glass rounded-2xl overflow-hidden hover:shadow-xl hover:-translate-y-1 transition-all duration-300 group flex flex-col">
      <div className="aspect-[4/3] bg-muted/30 relative overflow-hidden">
        {m.image ? (
          <img src={m.image} alt={m.label} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-muted-foreground text-sm">No photo yet</div>
        )}
        {m.store_count > 0 && <div className="absolute top-3 right-3 px-2 py-1 rounded-lg bg-indigo-500 text-white text-xs font-medium flex items-center gap-1"><Store className="w-3 h-3" /> {m.store_count} store{m.store_count === 1 ? "" : "s"}</div>}
      </div>
      <div className="p-4 flex flex-col flex-1">
        <div className="text-xs text-indigo-500 font-medium mb-1">{m.brand}{m.released ? ` · ${m.released.slice(0, 4)}` : ""}</div>
        <h3 className="font-semibold leading-snug mb-2 group-hover:text-indigo-500 transition-colors">{m.label}</h3>
        <ul className="text-xs text-muted-foreground space-y-0.5 mb-3">
          {specSummary(m.specs).slice(0, 4).map((part) => <li key={part}>{part}</li>)}
        </ul>
        <div className="mt-auto">
          {m.locked ? (
            <div className="inline-flex items-center gap-1.5 text-sm font-medium text-indigo-500"><Lock className="w-3.5 h-3.5" /> {m.store_count > 0 ? `Prices at ${m.store_count} store${m.store_count === 1 ? "" : "s"} with Pro` : "Prices with Pro"}</div>
          ) : m.lowest_price ? (
            <div><span className="text-xs text-muted-foreground">from </span><span className="text-lg font-bold tabular-nums">{formatPrice(m.lowest_price)}</span></div>
          ) : (
            <div className="text-sm text-muted-foreground">No store seen yet. Open to fetch.</div>
          )}
        </div>
      </div>
    </Link>
  );
}

function Browser({ category, title }: { category: string; title: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const [page, setPage] = useState<CatalogPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const brands = params.getAll("brand");
  const rams = params.getAll("ram");
  const storages = params.getAll("storage");
  const screen = params.get("screen");
  const price = params.get("price");
  const sort = params.get("sort") || "newest";

  const query = useMemo(() => {
    const q = new URLSearchParams();
    brands.forEach((b) => q.append("brand", b));
    rams.forEach((r) => q.append("ram", r));
    storages.forEach((s) => q.append("storage", s));
    const sb = SCREEN_BANDS.find((b) => b.key === screen);
    if (sb?.min !== undefined) q.set("min_screen", String(sb.min));
    if (sb?.max !== undefined) q.set("max_screen", String(sb.max));
    const pb = PRICE_BANDS.find((b) => b.key === price);
    if (pb?.min !== undefined) q.set("min_price", String(pb.min));
    if (pb?.max !== undefined) q.set("max_price", String(pb.max));
    q.set("sort", sort);
    return q.toString();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  useEffect(() => {
    let live = true;
    Promise.resolve().then(() => { if (live) { setLoading(true); setError(null); } });
    api.catalog(category, query)
      .then((p) => { if (live) setPage(p); })
      .catch((e: ApiError) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [category, query]);

  const update = (mutate: (q: URLSearchParams) => void) => {
    const q = new URLSearchParams(params.toString());
    mutate(q);
    router.push(`/catalog/${category}${q.toString() ? `?${q.toString()}` : ""}`);
  };
  const toggleMulti = (key: string, value: string) => update((q) => {
    const current = q.getAll(key);
    q.delete(key);
    (current.includes(value) ? current.filter((v) => v !== value) : [...current, value]).forEach((v) => q.append(key, v));
  });
  const setSingle = (key: string, value: string | null) => update((q) => { if (value === null || q.get(key) === value) q.delete(key); else q.set(key, value); });
  const activeCount = brands.length + rams.length + storages.length + (screen ? 1 : 0) + (price ? 1 : 0);

  const filters = page && (
    <div className="space-y-5">
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">Brand</div>
        <div className="flex flex-wrap gap-2">{page.facets.brands.map((f) => <Chip key={f.value} active={brands.includes(f.value)} onClick={() => toggleMulti("brand", f.value)}>{f.value} <span className="text-muted-foreground">{f.count}</span></Chip>)}</div>
      </div>
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">RAM</div>
        <div className="flex flex-wrap gap-2">{page.facets.ram_gb.map((f) => <Chip key={f.value} active={rams.includes(f.value)} onClick={() => toggleMulti("ram", f.value)}>{f.value}GB</Chip>)}</div>
        <p className="text-[11px] text-muted-foreground mt-1">Apple does not publish RAM; iPhones are not filtered by it.</p>
      </div>
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">Storage</div>
        <div className="flex flex-wrap gap-2">{page.facets.storage_gb.map((f) => <Chip key={f.value} active={storages.includes(f.value)} onClick={() => toggleMulti("storage", f.value)}>{storageLabel(Number(f.value))}</Chip>)}</div>
      </div>
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2">Screen size</div>
        <div className="flex flex-wrap gap-2">{SCREEN_BANDS.map((b) => <Chip key={b.key} active={screen === b.key} onClick={() => setSingle("screen", b.key)}>{b.label}</Chip>)}</div>
      </div>
      <div>
        <div className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">Price {page.locked && <Lock className="w-3 h-3 text-indigo-500" />}</div>
        {page.locked ? (
          <p className="text-xs text-muted-foreground">Filtering by price is part of Pro. <Link href="/pricing" className="text-indigo-500 hover:underline">See plans</Link></p>
        ) : (
          <div className="flex flex-wrap gap-2">{PRICE_BANDS.map((b) => <Chip key={b.key} active={price === b.key} onClick={() => setSingle("price", b.key)}>{b.label}</Chip>)}</div>
        )}
        {!page.locked && <p className="text-[11px] text-muted-foreground mt-1">By the lowest price a store currently lists.</p>}
      </div>
      {activeCount > 0 && <button type="button" onClick={() => router.push(`/catalog/${category}`)} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /> Clear filters</button>}
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-sm text-muted-foreground mt-1 flex items-center gap-1"><BadgeCheck className="w-4 h-4 text-indigo-500" /> Curated models with specifications from the makers. Pick one to see every size, colour and store.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {SORTS.map(([key, label]) => <button key={key} type="button" onClick={() => setSingle("sort", key === "newest" ? null : key)} className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${sort === key ? "bg-indigo-500/10 text-indigo-500" : "bg-muted/50 hover:bg-muted"}`}>{label}</button>)}
          <button type="button" onClick={() => setFiltersOpen((v) => !v)} className="lg:hidden inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-muted/50 hover:bg-muted"><SlidersHorizontal className="w-4 h-4" /> Filters{activeCount ? ` (${activeCount})` : ""}</button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <aside className={`lg:col-span-1 glass rounded-2xl p-5 h-fit ${filtersOpen ? "" : "hidden lg:block"}`} aria-label="Filters">
          {filters}
        </aside>
        <div className="lg:col-span-3">
          {loading && <Spinner label="Loading models…" className="py-10 justify-center" />}
          {error && <ErrorBox message={error} />}
          {!loading && page && page.models.length === 0 && <p className="text-muted-foreground py-10 text-center">No model matches these filters.</p>}
          {!loading && page && page.models.length > 0 && (
            <>
              <p className="text-sm text-muted-foreground mb-4">{page.total} model{page.total === 1 ? "" : "s"}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                {page.models.map((m) => <ModelCard key={m.line} m={m} />)}
              </div>
              <p className="text-xs text-muted-foreground mt-6">{page.specs_note} Prices are the lowest a store currently lists for any size of the model and change often.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CatalogBrowser(props: { category: string; title: string }) {
  return (
    <Suspense fallback={<div className="max-w-7xl mx-auto px-4 py-8"><div className="animate-shimmer h-96 rounded-2xl" /></div>}>
      <Browser {...props} />
    </Suspense>
  );
}
