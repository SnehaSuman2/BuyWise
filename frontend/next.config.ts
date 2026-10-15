import type { NextConfig } from "next";

/**
 * Origins the browser is allowed to talk to.
 *
 * The API origin is derived from NEXT_PUBLIC_API_URL rather than hard-coded, so the
 * policy stays correct wherever the app is deployed. Hard-coding it is how the
 * backend ends up blocked by our own CSP after a hosting change.
 */
function apiOrigin(): string {
  try {
    return new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").origin;
  } catch {
    return "http://localhost:8000";
  }
}

const isDev = process.env.NODE_ENV !== "production";

function productAnalyticsOrigins(): string[] {
  if (process.env.NEXT_PUBLIC_ANALYTICS_ENABLED !== "true") return [];
  const origins: string[] = [];
  const add = (value: string) => {
    try { origins.push(new URL(value).origin); } catch { /* Invalid hosts fail closed. */ }
  };
  if (process.env.NEXT_PUBLIC_MIXPANEL_TOKEN) {
    add(process.env.NEXT_PUBLIC_MIXPANEL_API_HOST || "https://api-js.mixpanel.com");
  }
  if (process.env.NEXT_PUBLIC_POSTHOG_KEY) {
    add(process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com");
    // PostHog fetches project configuration from its assets host.
    add("https://us-assets.i.posthog.com");
    add("https://eu-assets.i.posthog.com");
  }
  if (process.env.NEXT_PUBLIC_AMPLITUDE_API_KEY) {
    add(process.env.NEXT_PUBLIC_AMPLITUDE_SERVER_ZONE === "EU"
      ? "https://api.eu.amplitude.com" : "https://api2.amplitude.com");
  }
  return origins;
}

const connectSrc = [
  "'self'",
  apiOrigin(),
  "https://*.buywise.co.in",
  "https://accounts.google.com",
  "https://api.razorpay.com",
  "https://lumberjack.razorpay.com",
  // Google Analytics 4 (only loaded when NEXT_PUBLIC_GA_MEASUREMENT_ID is set)
  "https://*.google-analytics.com",
  "https://*.analytics.google.com",
  "https://*.googletagmanager.com",
  ...productAnalyticsOrigins(),
  ...(isDev ? ["http://localhost:8000", "http://127.0.0.1:8000"] : []),
];

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' https://accounts.google.com https://checkout.razorpay.com https://www.googletagmanager.com",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com",
      "font-src 'self' https://fonts.gstatic.com",
      "img-src 'self' data: https:",
      `connect-src ${Array.from(new Set(connectSrc)).join(" ")}`,
      "frame-src https://accounts.google.com https://api.razorpay.com https://checkout.razorpay.com",
      "frame-ancestors 'none'",
    ].join("; "),
  },
];

const nextConfig: NextConfig = {
  // Standalone output exists for the self-hosted Docker image, which copies
  // .next/standalone. Vercel builds its own output and fails on standalone, so
  // it is switched off there. VERCEL is set automatically during a Vercel build.
  ...(process.env.VERCEL ? {} : { output: "standalone" as const }),
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
  async redirects() {
    return [
      { source: "/auth/login", destination: "/login", permanent: true },
      { source: "/auth/register", destination: "/signup", permanent: true },
    ];
  },
};

export default nextConfig;
