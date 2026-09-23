"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { PriceHistoryData } from "./types";

/**
 * Price history for a product, fetched in the browser and shared.
 *
 * It has to happen here rather than while the page is rendered on the server,
 * because the server cannot see the reader's token and therefore always got a
 * withheld answer. Three parts of the product page want the same history, so
 * requests in flight are shared and one answer serves all of them.
 */
const inflight = new Map<string, Promise<PriceHistoryData | null>>();

export function usePriceHistory(productId: string, days = 90) {
  const { user } = useAuth();
  const [data, setData] = useState<PriceHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  // The answer depends on who is asking, so the viewer is part of the key.
  const key = `${productId}:${days}:${user?.id ?? "anon"}`;

  useEffect(() => {
    let live = true;
    Promise.resolve().then(() => { if (live) setLoading(true); });
    let request = inflight.get(key);
    if (!request) {
      request = api.history(productId, days).catch(() => null);
      inflight.set(key, request);
      // Held only long enough to join concurrent callers, not as a real cache.
      void request.finally(() => setTimeout(() => inflight.delete(key), 30_000));
    }
    void request
      .then((d) => { if (live) setData(d); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [key, productId, days]);

  return { history: data, loading };
}
