"use client";

import Script from "next/script";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { assignExperiment } from "@/lib/experiment";
import { GA_ID, pageview, flushAnalytics, track } from "@/lib/analytics";

/** Sends a page_view on every client-side route change. */
function RouteTracker() {
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    if (!pathname) return;
    pageview(pathname);
    if (!pathname.startsWith("/auth/")) {
      try {
        const method = sessionStorage.getItem("buywise:login-completed");
        if (method) { sessionStorage.removeItem("buywise:login-completed"); track("login", { method }); }
      } catch { /* storage may be unavailable */ }
    }
  }, [pathname, search]);
  return null;
}

/**
 * Google Analytics 4. Renders nothing unless a measurement id is configured, so
 * development and preview builds send no traffic. Page views are sent manually on
 * route changes because the app navigates client-side.
 */
export default function Analytics() {
  const pathname = usePathname();
  const [enabled, setEnabled] = useState(false);
  useEffect(() => { Promise.resolve().then(() => setEnabled(!assignExperiment().preview)); }, []);
  if (!GA_ID || !enabled || pathname.startsWith("/auth/callback")) return null;
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
      <Script id="ga4-init" strategy="afterInteractive" onReady={flushAnalytics}>
        {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA_ID}', { send_page_view: false, anonymize_ip: true, page_location: window.location.origin + window.location.pathname, page_referrer: '' });`}
      </Script>
      <Suspense fallback={null}>
        <RouteTracker />
      </Suspense>
    </>
  );
}
