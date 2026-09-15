import type { MetadataRoute } from "next";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

/** Static, high-quality pages only. Product pages are indexed via canonical links, not bulk-generated. */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ["/", "/agent", "/pricing", "/trust-methodology", "/affiliate-disclosure", "/privacy", "/terms"].map((path) => ({
    url: `${APP_URL}${path}`,
    lastModified: now,
    changeFrequency: path === "/" ? "daily" : "monthly",
    priority: path === "/" ? 1 : 0.6,
  }));
}
