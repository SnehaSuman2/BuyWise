"use client";

import { Suspense, useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { identifyUser, isAnalyticsEnabled, reconcileAnonymous, trackEvent } from "@/lib/product-analytics";

function Tracker() {
  const pathname = usePathname();
  const search = useSearchParams();
  const { user, loading } = useAuth();
  const identity = useRef<string | null>(null);
  const lastLocation = useRef<string | null>(null);
  const diagnosed = useRef(false);
  const location = `${pathname}?${search.toString()}`;

  useEffect(() => {
    const enabled = isAnalyticsEnabled();
    if (!diagnosed.current) {
      diagnosed.current = true;
      // Temporary startup diagnostics: booleans only, never credentials or URLs.
      console.info("[analytics]", {
        enabled,
        mixpanelConfigured: Boolean(process.env.NEXT_PUBLIC_MIXPANEL_TOKEN),
        posthogConfigured: Boolean(process.env.NEXT_PUBLIC_POSTHOG_KEY),
        amplitudeConfigured: Boolean(process.env.NEXT_PUBLIC_AMPLITUDE_API_KEY),
      });
    }
    if (!enabled) return;

    const anonymous = () => {
      if (identity.current === "anonymous") return;
      identity.current = "anonymous";
      reconcileAnonymous();
    };
    // The existing authentication client can retry a cold backend for 90 seconds.
    // Release anonymous analytics after five seconds without blocking the app.
    if (loading) {
      const timeout = setTimeout(anonymous, 5000);
      return () => clearTimeout(timeout);
    }
    if (user) {
      if (identity.current !== user.id) {
        identity.current = user.id;
        identifyUser(user);
      }
    } else anonymous();
  }, [loading, user]);

  useEffect(() => {
    if (lastLocation.current === location) return;
    lastLocation.current = location;
    trackEvent("page_viewed", { path: pathname });
  }, [location, pathname]);

  return null;
}

export default function ProductAnalytics() {
  return <Suspense fallback={null}><Tracker /></Suspense>;
}
