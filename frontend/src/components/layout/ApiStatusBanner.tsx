"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import type { ApiState } from "@/lib/api";

/** Shown while a request is waiting for the API host to boot after a quiet period. */
export default function ApiStatusBanner() {
  const [waking, setWaking] = useState(false);
  useEffect(() => {
    const onState = (e: Event) => setWaking((e as CustomEvent<ApiState>).detail === "waking");
    window.addEventListener("buywise:api", onState);
    return () => window.removeEventListener("buywise:api", onState);
  }, []);
  if (!waking) return null;
  return (
    <div role="status" className="sticky top-0 z-50 bg-indigo-500 text-white text-sm px-4 py-2 flex items-center justify-center gap-2">
      <Loader2 className="w-4 h-4 animate-spin" />
      Waking up the BuyWise server. After a quiet period this takes up to a minute; your request will continue automatically.
    </div>
  );
}
