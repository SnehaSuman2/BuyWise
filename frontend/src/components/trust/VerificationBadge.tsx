import { ShieldCheck, ShieldQuestion } from "lucide-react";

/**
 * Says plainly how much BuyWise knows about a seller.
 *
 * "Unverified" is not an accusation — it means this merchant has not been assessed
 * yet. Small retailers earn a real score from evidence over time, never by paying.
 */
export default function VerificationBadge({
  verification,
  className = "",
}: {
  verification?: "verified" | "unverified" | "flagged";
  className?: string;
}) {
  if (verification !== "unverified") return null;
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide bg-amber-500/10 text-amber-600 border border-amber-500/30 ${className}`}
      title="BuyWise hasn't assessed this seller yet. We're gathering evidence about it — treat the price with normal caution until then."
    >
      <ShieldQuestion className="w-3 h-3" />
      Unverified seller
    </span>
  );
}

export function VerifiedTick({ verification }: { verification?: string }) {
  if (verification !== "verified") return null;
  return <ShieldCheck className="w-3 h-3 text-emerald-500" aria-label="Verified seller" />;
}
