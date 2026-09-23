"use client";

import { useState } from "react";
import { TrendingDown } from "lucide-react";
import { formatPrice } from "@/lib/utils";
import { usePriceHistory } from "@/lib/usePriceHistory";
import DataBadge from "@/components/ui/DataBadge";
import LockedPanel from "@/components/product/LockedPanel";
import PriceHistoryChart from "@/components/product/PriceHistoryChart";
import type { PriceHistoryData } from "@/lib/types";

/** Windows to offer. The server caps whatever the viewer's plan does not cover. */
const WINDOWS: { key: string; label: string; days: number }[] = [
  { key: "7d", label: "7 days", days: 7 },
  { key: "1m", label: "1 month", days: 30 },
  { key: "3m", label: "3 months", days: 90 },
  { key: "6m", label: "6 months", days: 180 },
  { key: "1y", label: "1 year", days: 365 },
];

/**
 * Price history, fetched in the browser.
 *
 * It used to be fetched while rendering the page on the server, which has no
 * access to the reader's token because that lives in their browser. Every
 * request was therefore anonymous, so the answer always came back locked and a
 * paying subscriber was shown an advertisement for the plan they already had.
 */
export default function PriceHistorySection({
  productId,
  initial,
}: {
  productId: string;
  initial: PriceHistoryData | null;
}) {
  const [days, setDays] = useState(90);
  const { history: fetched, loading } = usePriceHistory(productId, days);
  const data = fetched ?? initial;

  const stats = data?.stats ?? null;
  const enough = Boolean(stats && stats.observations >= 2);

  return (
    <section id="history" className="mb-16">
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <TrendingDown className="w-6 h-6 text-purple-500" /> Price history
        </h2>
        {data && !data.locked && <DataBadge meta={data.meta} />}
        {!data?.locked && (
          <div className="flex items-center gap-1 ml-auto flex-wrap">
            {WINDOWS.map((w) => (
              <button
                key={w.key}
                type="button"
                onClick={() => setDays(w.days)}
                aria-pressed={days === w.days}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${days === w.days ? "bg-purple-500/10 text-purple-500" : "bg-muted/50 hover:bg-muted text-muted-foreground"}`}
              >
                {w.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {data?.locked ? (
        <LockedPanel what="price history" />
      ) : loading && !data ? (
        <div className="animate-shimmer h-56 rounded-2xl" />
      ) : enough && stats ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {[
              { label: "Current lowest", value: formatPrice(stats.current_price) },
              { label: "30-day average", value: stats.average_30d ? formatPrice(stats.average_30d) : "—" },
              { label: "90-day average", value: stats.average_90d ? formatPrice(stats.average_90d) : "—" },
              { label: "Recorded low / high", value: `${formatPrice(stats.historical_low)} / ${formatPrice(stats.historical_high)}` },
            ].map((s) => (
              <div key={s.label} className="glass rounded-xl p-4 text-center">
                <div className="text-xs text-muted-foreground mb-1">{s.label}</div>
                <div className="text-lg font-bold tabular-nums">{s.value}</div>
              </div>
            ))}
          </div>
          <div className="glass rounded-2xl p-4"><PriceHistoryChart data={data!} /></div>
          <p className="text-xs text-muted-foreground mt-3">
            {stats.observations} daily observations over {stats.span_days} days · trend: {stats.trend}. {data!.message}
          </p>
        </>
      ) : stats ? (
        <div className="glass rounded-2xl p-6">
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 mb-3">
            <div>
              <div className="text-xs text-muted-foreground">Price recorded</div>
              <div className="text-2xl font-bold tabular-nums">{formatPrice(stats.current_price)}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Tracking started</div>
              <div className="text-lg font-semibold">
                {data?.history?.[0] ? new Date(data.history[0].date).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" }) : "today"}
              </div>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">{data?.message}</p>
          <p className="text-sm text-muted-foreground mt-2">
            A chart needs prices seen on two different days. Save this product or set an alert and BuyWise re-checks it for you; a buy-or-wait signal appears once there are seven days of observations.
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No price history recorded for this product yet.</p>
      )}
    </section>
  );
}
