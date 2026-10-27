"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Check, ChevronRight } from "lucide-react";
import { assignExperiment } from "@/lib/experiment";
import { track } from "@/lib/analytics";

export default function ShoppingJourney({ step, productId }: { step: 0 | 1; productId?: string }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    Promise.resolve().then(() => setVisible(assignExperiment().variant === "b"));
    if (productId) track("view_product", { product_id: productId });
  }, [productId]);
  if (!visible) return null;
  return <div className="mb-7 rounded-xl border border-border bg-muted/40 p-4">
    <ol aria-label="Shopping progress" className="flex flex-wrap gap-x-3 gap-y-2 text-xs sm:text-sm">
      {["Find a product", "Compare offers", "Choose or track"].map((label, i) => <li key={label} aria-current={i === step ? "step" : undefined} className={`flex items-center gap-2 ${i === step ? "font-semibold text-indigo-600 dark:text-indigo-400" : "text-muted-foreground"}`}>
        <span className="w-5 h-5 rounded-full border border-current flex items-center justify-center text-[10px]">{i < step ? <Check size={12} /> : i + 1}</span>{i < step ? <Link href="/" className="underline underline-offset-2">{label}</Link> : label}{i < 2 && <ChevronRight size={14} aria-hidden="true" />}
      </li>)}
    </ol>
    <p className="mt-3 text-xs text-muted-foreground leading-relaxed">{step === 0 ? "Choose a product to compare its offers. Check the model, storage and colour before continuing." : "Compare the total cost and seller details below. Buy on the retailer’s site, or set an alert to wait for a better price."}</p>
  </div>;
}
