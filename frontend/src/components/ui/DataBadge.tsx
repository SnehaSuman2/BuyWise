import { FlaskConical, Radio } from "lucide-react";
import type { DataMeta } from "@/lib/types";

/** Every data-bearing view says whether it shows simulated or live data. */
export default function DataBadge({ meta, className = "" }: { meta?: DataMeta | null | { is_demo: boolean; data_mode?: string }; className?: string }) {
  if (!meta) return null;
  const demo = meta.is_demo;
  const mixed = "data_mode" in meta && meta.data_mode === "mixed";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold uppercase tracking-wide border ${demo ? "bg-amber-500/10 text-amber-600 border-amber-500/30" : "bg-emerald-500/10 text-emerald-600 border-emerald-500/30"} ${className}`} title={demo ? "Simulated data — configure live providers to replace it" : "Live data from configured providers"}>
      {demo ? <FlaskConical className="w-3 h-3" /> : <Radio className="w-3 h-3" />}
      {demo ? (mixed ? "Mixed demo data" : "Demo data") : "Live data"}
    </span>
  );
}
