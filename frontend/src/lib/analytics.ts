/**
 * Google Analytics 4, enabled only when NEXT_PUBLIC_GA_MEASUREMENT_ID is set.
 *
 * Rules: never send personal data (no emails, names, user ids, order references).
 * Events carry product ids, retailer names and query types, which is enough to see
 * what people search for and where they go, and nothing that identifies them.
 */

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
  if (!analyticsEnabled()) return;
  const clean: Params = {};
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") clean[k] = v;
  try { window.gtag!("event", event, clean); } catch { /* analytics must never break the page */ }
}

export function pageview(path: string): void {
  if (!analyticsEnabled()) return;
  try { window.gtag!("event", "page_view", { page_path: path, page_location: window.location.href, page_title: document.title }); } catch { /* ignore */ }
}
