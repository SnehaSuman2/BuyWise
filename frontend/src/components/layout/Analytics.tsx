"use client";

import Script from "next/script";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";
import { GA_ID, pageview } from "@/lib/analytics";

/** Sends a page_view on every client-side route change. */
function RouteTracker() {
  const pathname = usePathname();
  const search = useSearchParams();
  useEffect(() => {
    if (!pathname) return;
    const qs = search?.toString();
    pageview(qs ? `${pathname}?${qs}` : pathname);
  }, [pathname, search]);
  return null;
}

/**
 * Google Analytics 4. Renders nothing unless a measurement id is configured, so
 * development and preview builds send no traffic. Page views are sent manually on
 * route changes because the app navigates client-side.
 */
export default function Analytics() {
  if (!GA_ID) return null;
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
      <Script id="ga4-init" strategy="afterInteractive">
        {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA_ID}', { send_page_view: false, anonymize_ip: true });`}
      </Script>
      <Suspense fallback={null}>
        <RouteTracker />
      </Suspense>
    </>
  );
}
