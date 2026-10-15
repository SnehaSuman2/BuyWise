/**
 * Google Analytics 4, enabled only when NEXT_PUBLIC_GA_MEASUREMENT_ID is set.
 *
 * Rules: never send personal data (no emails, names, user ids, order references).
 * Events carry product ids, retailer names and query types, which is enough to see
 * what people search for and where they go, and nothing that identifies them.
 */

import { trackEvent } from "./product-analytics";

export const GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID || "";

type Params = Record<string, string | number | boolean | undefined>;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

export function analyticsEnabled(): boolean {
  return Boolean(GA_ID) && typeof window !== "undefined" && typeof window.gtag === "function";
}

export function track(event: string, params: Params = {}): void {
  // Existing search results feed the product SDKs independently of GA.
  // Never forward search_term, URLs, or the unrestricted legacy params object.
  if (event === "search" && (params.query_type === "text" || params.query_type === "url" || params.query_type === "image")
    && typeof params.results === "number" && Number.isInteger(params.results) && params.results >= 0
    && (params.data_mode === "live" || params.data_mode === "demo" || params.data_mode === "mixed")) {
    trackEvent("search_results_viewed", {
      query_type: params.query_type,
      result_count: params.results,
      is_demo: params.data_mode !== "live",
    });
  }
  if (!analyticsEnabled()) return;
  const clean: Params = {};
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") clean[k] = v;
  try { window.gtag!("event", event, clean); } catch { /* analytics must never break the page */ }
}

export function pageview(path: string): void {
  if (!analyticsEnabled()) return;
  try { window.gtag!("event", "page_view", { page_path: path, page_location: window.location.href, page_title: document.title }); } catch { /* ignore */ }
}
