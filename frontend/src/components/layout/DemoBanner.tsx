"use client";
import { useState } from "react";
import { X, FlaskConical, WifiOff } from "lucide-react";
import { useMeta } from "@/lib/meta";

export default function DemoBanner() {
  const [dismissed, setDismissed] = useState(false);
  const { meta, loading, error } = useMeta();
  if (dismissed || loading) return null;
  if (error) {
    return (
      <div className="bg-rose-500/10 border-b border-rose-500/20">
        <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-2 text-sm text-rose-600">
          <WifiOff className="w-4 h-4" /> <span className="font-medium">API unreachable</span>
          <span className="hidden sm:inline text-rose-600/70">— start the backend (see README) to load data.</span>
        </div>
      </div>
    );
  }
  if (!meta?.demo_mode) return null;
  return (
    <div className="bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-amber-500/10 border-b border-amber-500/20">
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
          <FlaskConical className="w-4 h-4" />
          <span className="font-medium">Demo mode</span>
          <span className="hidden sm:inline text-amber-600/70 dark:text-amber-400/70">— showing simulated products, prices and trust evidence. Add SERPAPI_API_KEY to switch to live data.</span>
        </div>
        <button onClick={() => setDismissed(true)} className="p-1 hover:bg-amber-500/10 rounded transition-colors" aria-label="Dismiss"><X className="w-4 h-4 text-amber-600 dark:text-amber-400" /></button>
      </div>
    </div>
  );
}
