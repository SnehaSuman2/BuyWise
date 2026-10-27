import { assignExperiment, EXPERIMENT_ID, experimentContext } from "./experiment";
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

const pending: Array<[string, Params]> = [];
export function flushAnalytics() {
  if (!analyticsEnabled()) return;
  for (const [event, params] of pending.splice(0)) window.gtag!("event", event, params);
}

export function track(event: string, params: Params = {}): void {
  if (typeof window === "undefined") return;
  const assignment = experimentContext() || assignExperiment();
  if (assignment.preview || !GA_ID || window.location.pathname.startsWith("/auth/callback")) return;
  const clean: Params = { experiment_id: EXPERIMENT_ID, variant: assignment.variant, experiment_mode: assignment.mode, page_location: window.location.origin + window.location.pathname, page_referrer: "" };
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") clean[k] = v;
  if (!analyticsEnabled()) { if (pending.length < 100) pending.push([event, clean]); return; }
  try { window.gtag!("event", event, clean); } catch { /* analytics must never break the page */ }
}

export function pageview(path: string): void {
  const cleanPath = path.split("?")[0];
  if (cleanPath.startsWith("/auth/callback")) return;
  track("page_view", { page_path: cleanPath, page_location: window.location.origin + cleanPath, page_title: document.title });
}
