"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import type { PriceHistoryData } from "@/lib/types";
import { formatPrice } from "@/lib/utils";

export default function PriceHistoryChart({ data }: { data: PriceHistoryData }) {
  if (!data.history.length) return null;
  const points = data.history.map((p) => ({ date: new Date(p.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" }), price: p.price }));
  const avg = data.stats?.average_90d ?? data.stats?.average_30d ?? null;
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={24} stroke="currentColor" opacity={0.5} />
          <YAxis tick={{ fontSize: 11 }} width={70} tickFormatter={(v: number) => `₹${Math.round(v / 1000)}k`} domain={["auto", "auto"]} stroke="currentColor" opacity={0.5} />
          <Tooltip formatter={(value) => [formatPrice(Number(value)), "Lowest price"]} contentStyle={{ borderRadius: 12, fontSize: 12 }} />
          {avg && <ReferenceLine y={avg} stroke="#a78bfa" strokeDasharray="4 4" label={{ value: "avg", fontSize: 10, fill: "#a78bfa" }} />}
          <Line type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
