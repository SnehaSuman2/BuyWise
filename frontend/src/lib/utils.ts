/** Utility functions for BuyWise */

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(amount: number | null | undefined, currency: string = "INR"): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "—";
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  if (days > 30) return formatDate(dateStr);
  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return "Just now";
}

export function getTrustColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted-foreground";
  if (score >= 75) return "trust-high";
  if (score >= 55) return "trust-medium";
  return "trust-low";
}

export function getTrustBgColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "bg-muted/40 border-border/40";
  if (score >= 75) return "trust-bg-high";
  if (score >= 55) return "trust-bg-medium";
  return "trust-bg-low";
}

export function riskLabel(risk: string): string {
  return { low: "Low risk", medium: "Medium risk", high: "Higher risk", unknown: "Not enough evidence" }[risk] || risk;
}

export function priceStatusLabel(status: string): string {
  return { GOOD_DEAL: "Good deal", AVERAGE_PRICE: "Average price", HIGH_PRICE: "High price", UNKNOWN: "Not enough history" }[status] || status;
}

export function priceActionLabel(action: string): string {
  return { BUY_NOW: "Buy now", WAIT: "Wait", NEUTRAL: "Fair price", INSUFFICIENT_DATA: "Not enough history" }[action] || action;
}

export function getPriceActionColor(action: string): string {
  switch (action) {
    case "BUY_NOW": return "text-emerald-500";
    case "WAIT": return "text-amber-500";
    default: return "text-muted-foreground";
  }
}

export function getRecCategoryColor(category: string): string {
  switch (category) {
    case "BEST_OVERALL": return "bg-gradient-to-r from-indigo-500 to-purple-500 text-white border-transparent";
    case "CHEAPEST": return "bg-emerald-500/10 text-emerald-600 border-emerald-500/30";
    case "SAFEST": return "bg-blue-500/10 text-blue-600 border-blue-500/30";
    case "BEST_VALUE": return "bg-amber-500/10 text-amber-600 border-amber-500/30";
    case "FASTEST": return "bg-rose-500/10 text-rose-600 border-rose-500/30";
    default: return "bg-muted text-muted-foreground";
  }
}

export function getRecCategoryLabel(category: string): string {
  switch (category) {
    case "BEST_OVERALL": return "Best overall";
    case "CHEAPEST": return "Cheapest";
    case "SAFEST": return "Safest";
    case "BEST_VALUE": return "Best value";
    case "FASTEST": return "Fastest";
    default: return category;
  }
}

export function matchBadgeClass(matchType: string): string {
  switch (matchType) {
    case "exact_match": return "bg-emerald-500/10 text-emerald-600 border-emerald-500/30";
    case "same_product_different_variant": return "bg-amber-500/10 text-amber-600 border-amber-500/30";
    case "similar_product": return "bg-slate-500/10 text-slate-600 border-slate-500/30";
    default: return "bg-muted text-muted-foreground border-border/40";
  }
}

export function getInitials(name: string): string {
  return name.split(" ").map((w) => w[0]).join("").toUpperCase().slice(0, 2);
}
