"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import FamilyPanel from "@/components/product/FamilyPanel";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { ProductFamily } from "@/lib/types";

/** Fetched on the client so a signed-in Pro viewer gets the prices the server unlocks for them. */
export default function FamilyView({ line }: { line: string }) {
  const [family, setFamily] = useState<ProductFamily | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    // State is only touched from promise callbacks, never synchronously in the effect.
    Promise.resolve().then(() => { if (live) { setLoading(true); setFamily(null); setError(null); } });
    api.family(line)
      .then((f) => { if (live) setFamily(f); })
      .catch((e: ApiError) => { if (live) setError(e.status === 404 ? "BuyWise has not seen this product line yet. Search for it to fetch stores." : e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [line]);
  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <Link href="/search" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"><ArrowLeft className="w-4 h-4" /> Back to search</Link>
      {loading && <Spinner label="Gathering every store…" className="py-10 justify-center" />}
      {error && <ErrorBox message={error} />}
      {family && <FamilyPanel family={family} />}
    </div>
  );
}
