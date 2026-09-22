"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Lock, Store, BadgeCheck, X, SlidersHorizontal } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { specSummary, storageLabel } from "@/lib/specs";
import Spinner from "@/components/ui/Spinner";
import type { CatalogPage, CatalogModelCard, CatalogFilters } from "@/lib/types";

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

type State = { brands: string[]; rams: string[]; storages: string[]; screen: string | null; price: { min?: number; max?: number } | null; priceKey: string | null; sort: string };

function fromQuery(f: CatalogFilters | null | undefined): State {
  const price = f && (f.min_price !== undefined || f.max_price !== undefined) ? { min: f.min_price, max: f.max_price } : null;
  const priceKey = price ? (PRICE_BANDS.find((b) => b.min === price.min && b.max === price.max)?.key ?? "custom") : null;
  return {
    brands: f?.brands ?? [],
    rams: (f?.ram_gb ?? []).map(String),
    storages: (f?.storage_gb ?? []).map(String),
    screen: null,
    price,
    priceKey,
    sort: price ? "price_asc" : "newest",
  };
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" onClick={onClick} aria-pressed={active} className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${active ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40 hover:bg-muted/50"}`}>{children}</button>;
}

function ModelCard({ m }: { m: CatalogModelCard }) {
  return (
    <Link href={`/family/${encodeURIComponent(m.line)}`} className="glass rounded-2xl overflow-hidden hover:shadow-xl hover:-translate-y-1 transition-all duration-300 group flex flex-col">
      <div className="aspect-[4/3] bg-muted/30 relative overflow-hidden">
        {m.image ? <img src={m.image} alt={m.label} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" /> : <div className="w-full h-full flex items-center justify-center text-muted-foreground text-sm">No photo yet</div>}
        {m.store_count > 0 && <div className="absolute top-3 right-3 px-2 py-1 rounded-lg bg-indigo-500 text-white text-xs font-medium flex items-center gap-1"><Store className="w-3 h-3" /> {m.store_count} store{m.store_count === 1 ? "" : "s"}</div>}
      </div>
      <div className="p-4 flex flex-col flex-1">
        <div className="text-xs text-indigo-500 font-medium mb-1">{m.brand}{m.released ? ` · ${m.released.slice(0, 4)}` : ""}</div>
        <h3 className="font-semibold leading-snug mb-2 group-hover:text-indigo-500 transition-colors">{m.label}</h3>
        <ul className="text-xs text-muted-foreground space-y-0.5 mb-3">{specSummary(m.specs).slice(0, 4).map((part) => <li key={part}>{part}</li>)}</ul>
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

/**
 * Curated models that fit a category-style search, with the filters the query
 * implied already chosen. Changing a filter asks the server again; prices and
 * the price filter are withheld there for viewers without Pro.
 */
export default function SpecPanel({ initial, filters }: { initial: CatalogPage; filters: CatalogFilters | null | undefined }) {
  const [state, setState] = useState<State>(() => fromQuery(filters));
  const [page, setPage] = useState<CatalogPage>(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(true);

  const query = useMemo(() => {
    const q = new URLSearchParams();
    state.brands.forEach((b) => q.append("brand", b));
    state.rams.forEach((r) => q.append("ram", r));
    state.storages.forEach((s) => q.append("storage", s));
    const sb = SCREEN_BANDS.find((b) => b.key === state.screen);
    if (sb?.min !== undefined) q.set("min_screen", String(sb.min));
    if (sb?.max !== undefined) q.set("max_screen", String(sb.max));
    if (state.price?.min !== undefined) q.set("min_price", String(state.price.min));
    if (state.price?.max !== undefined) q.set("max_price", String(state.price.max));
    q.set("sort", state.sort);
    return q.toString();
  }, [state]);

  // The first render shows what the search already returned; only a change refetches.
  const [initialQuery] = useState(query);
  useEffect(() => {
    if (query === initialQuery) return;
    let live = true;
    Promise.resolve().then(() => { if (live) { setLoading(true); setError(null); } });
    api.catalog(initial.category, query)
      .then((p) => { if (live) setPage(p); })
      .catch((e: ApiError) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [query, initialQuery, initial.category]);

  const toggle = (key: "brands" | "rams" | "storages", value: string) => setState((s) => ({ ...s, [key]: s[key].includes(value) ? s[key].filter((v) => v !== value) : [...s[key], value] }));
  const setPrice = (band: (typeof PRICE_BANDS)[number]) => setState((s) => s.priceKey === band.key ? { ...s, price: null, priceKey: null } : { ...s, price: { min: band.min, max: band.max }, priceKey: band.key, sort: s.sort === "newest" ? "price_asc" : s.sort });
  const active = state.brands.length + state.rams.length + state.storages.length + (state.screen ? 1 : 0) + (state.price ? 1 : 0);
  const clear = () => setState({ brands: [], rams: [], storages: [], screen: null, price: null, priceKey: null, sort: "newest" });

  return (
    <section className="glass rounded-2xl p-5 sm:p-6 mb-8 animate-fade-in" aria-label="Filter by specifications">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2"><SlidersHorizontal className="w-5 h-5 text-indigo-500" /> {page.title} by specification</h2>
          <p className="text-sm text-muted-foreground mt-1 flex items-center gap-1"><BadgeCheck className="w-4 h-4 text-indigo-500" /> Curated models with specs from the makers. Pick one to see every size, colour and store.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {SORTS.map(([key, label]) => <button key={key} type="button" onClick={() => setState((s) => ({ ...s, sort: key }))} className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${state.sort === key ? "bg-indigo-500/10 text-indigo-500" : "bg-muted/50 hover:bg-muted"}`}>{label}</button>)}
          <button type="button" onClick={() => setOpen((v) => !v)} className="sm:hidden inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-muted/50 hover:bg-muted">Filters{active ? ` (${active})` : ""}</button>
        </div>
      </div>

      <div className={`space-y-3 mb-5 ${open ? "" : "hidden sm:block"}`}>
        <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-medium text-muted-foreground w-16">Brand</span>{page.facets.brands.map((f) => <Chip key={f.value} active={state.brands.includes(f.value)} onClick={() => toggle("brands", f.value)}>{f.value}</Chip>)}</div>
        <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-medium text-muted-foreground w-16" title="Apple does not publish RAM; iPhones are not filtered by it">RAM</span>{page.facets.ram_gb.map((f) => <Chip key={f.value} active={state.rams.includes(f.value)} onClick={() => toggle("rams", f.value)}>{f.value}GB</Chip>)}</div>
        <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-medium text-muted-foreground w-16">Storage</span>{page.facets.storage_gb.map((f) => <Chip key={f.value} active={state.storages.includes(f.value)} onClick={() => toggle("storages", f.value)}>{storageLabel(Number(f.value))}</Chip>)}</div>
        <div className="flex flex-wrap items-center gap-2"><span className="text-xs font-medium text-muted-foreground w-16">Screen</span>{SCREEN_BANDS.map((b) => <Chip key={b.key} active={state.screen === b.key} onClick={() => setState((s) => ({ ...s, screen: s.screen === b.key ? null : b.key }))}>{b.label}</Chip>)}</div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground w-16 flex items-center gap-1">Price {page.locked && <Lock className="w-3 h-3 text-indigo-500" />}</span>
          {page.locked ? (
            <span className="text-xs text-muted-foreground">Filtering by price is part of Pro. <Link href="/pricing" className="text-indigo-500 hover:underline">See plans</Link></span>
          ) : (
            <>
              {PRICE_BANDS.map((b) => <Chip key={b.key} active={state.priceKey === b.key} onClick={() => setPrice(b)}>{b.label}</Chip>)}
              {state.priceKey === "custom" && state.price && <Chip active onClick={() => setState((s) => ({ ...s, price: null, priceKey: null }))}>{state.price.min ? `${formatPrice(state.price.min)} to ` : "Under "}{state.price.max ? formatPrice(state.price.max) : "any"} <X className="w-3 h-3 inline" /></Chip>}
            </>
          )}
        </div>
        {active > 0 && <button type="button" onClick={clear} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /> Clear filters</button>}
      </div>

      {loading && <Spinner label="Filtering…" className="py-6 justify-center" />}
      {error && <p className="text-sm text-rose-500">{error}</p>}
      {!loading && page.models.length === 0 && <p className="text-sm text-muted-foreground py-6 text-center">No curated model matches these filters.{page.locked ? "" : " Widen the price band or clear a filter."}</p>}
      {!loading && page.models.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">{page.models.map((m) => <ModelCard key={m.line} m={m} />)}</div>
          <p className="text-xs text-muted-foreground mt-4">{page.total} model{page.total === 1 ? "" : "s"}. {page.specs_note} Prices are the lowest a store currently lists for any size of the model.</p>
        </>
      )}
    </section>
  );
}
