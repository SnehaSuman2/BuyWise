"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ShieldCheck, Check, X, EyeOff, BadgeCheck, Star, ArrowLeft } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/utils";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { CommunityReport } from "@/lib/types";

const TABS = [
  { key: "pending", label: "Pending" },
  { key: "approved", label: "Approved" },
  { key: "rejected", label: "Rejected" },
  { key: "hidden", label: "Hidden (auto-flagged)" },
] as const;

const ACTIONS: { action: string; label: string; icon: typeof Check; tone: string }[] = [
  { action: "approve", label: "Publish", icon: Check, tone: "text-emerald-600 border-emerald-500/30 hover:bg-emerald-500/10" },
  { action: "reject", label: "Reject", icon: X, tone: "text-rose-600 border-rose-500/30 hover:bg-rose-500/10" },
  { action: "hide", label: "Hide", icon: EyeOff, tone: "text-amber-600 border-amber-500/30 hover:bg-amber-500/10" },
  { action: "verify", label: "Mark verified", icon: BadgeCheck, tone: "text-indigo-600 border-indigo-500/30 hover:bg-indigo-500/10" },
];

/** Admin-only queue for community experiences. The server enforces the admin role; this page only reflects it. */
export default function ModerationPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<string>("pending");
  const [reports, setReports] = useState<CommunityReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      router.replace("/login?next=/admin/moderation");
      return;
    }
    if (user.role !== "admin") return;
    let live = true;
    api
      .moderationQueue(status)
      .then((rows) => live && setReports(rows))
      .catch((e: ApiError) => {
        if (!live) return;
        setError(e.message);
        setReports([]);
      });
    return () => {
      live = false;
    };
  }, [authLoading, user, status, router]);

  const act = async (id: string, action: string) => {
    setBusyId(id);
    setError(null);
    try {
      await api.moderateReport(id, action);
      setReports((prev) => (prev ? prev.filter((r) => r.id !== id) : prev));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusyId(null);
    }
  };

  if (authLoading) return <div className="max-w-4xl mx-auto px-4 py-12"><Spinner label="Checking access…" /></div>;

  if (user && user.role !== "admin") {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center">
        <ShieldCheck className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
        <h1 className="text-xl font-bold mb-2">Moderation is admin-only</h1>
        <p className="text-sm text-muted-foreground">
          Your account does not have the admin role. Ask a BuyWise admin to grant it.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6">
        <ArrowLeft className="w-4 h-4" /> Back
      </Link>
      <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
        <ShieldCheck className="w-6 h-6 text-indigo-500" /> Community moderation
      </h1>
      <p className="text-sm text-muted-foreground mb-6">
        Experiences stay unpublished until approved here. Reject anything promotional, abusive, or
        impossible to have happened. Merchants may not pay for an outcome on this screen.
      </p>

      <div className="flex gap-2 mb-6">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => {
              setReports(null);
              setError(null);
              setStatus(t.key);
            }}
            className={`px-4 py-2 rounded-xl text-sm font-medium border transition-colors ${
              status === t.key ? "border-indigo-500 bg-indigo-500/10 text-indigo-500" : "border-border/40 hover:bg-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && <ErrorBox message={error} className="mb-4" />}
      {reports === null && <Spinner label="Loading queue…" />}
      {reports && reports.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">Nothing in the {status} queue.</p>
      )}

      <ul className="space-y-4">
        {(reports || []).map((r) => (
          <li key={r.id} className="glass rounded-2xl p-5">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              {r.rating ? (
                <span className="flex items-center gap-0.5 text-amber-500 text-sm font-medium">
                  <Star className="w-3.5 h-3.5 fill-current" />
                  {r.rating}
                </span>
              ) : null}
              {r.title && <span className="font-semibold text-sm">{r.title}</span>}
              <span className="text-xs px-2 py-0.5 rounded bg-muted/50 capitalize">{r.report_type}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-muted/50">
                verification: {r.verification_status}
              </span>
              {r.flag_count > 0 && (
                <span className="text-xs px-2 py-0.5 rounded bg-rose-500/10 text-rose-600">
                  {r.flag_count} flag{r.flag_count > 1 ? "s" : ""}
                </span>
              )}
              {r.helpful_count > 0 && <span className="text-xs text-muted-foreground">{r.helpful_count} helpful</span>}
            </div>
            <p className="text-sm whitespace-pre-wrap mb-3">{r.body}</p>
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground mb-3">
              <span>{r.username ?? "BuyWise user"}</span>
              <span>{formatRelativeTime(r.created_at)}</span>
              {r.product_id && (
                <Link href={`/product/${r.product_id}`} className="text-indigo-500 hover:underline">
                  View product
                </Link>
              )}
              {r.retailer_id && (
                <Link href={`/retailer/${r.retailer_id}`} className="text-indigo-500 hover:underline">
                  View retailer
                </Link>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {ACTIONS.map(({ action, label, icon: Icon, tone }) => (
                <button
                  key={action}
                  onClick={() => act(r.id, action)}
                  disabled={busyId === r.id}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors disabled:opacity-50 ${tone}`}
                >
                  <Icon className="w-3.5 h-3.5" /> {label}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
