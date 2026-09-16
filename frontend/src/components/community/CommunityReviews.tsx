"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquarePlus, ShieldCheck, Flag, Star, CheckCircle2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/utils";
import Spinner from "@/components/ui/Spinner";
import ErrorBox from "@/components/ui/ErrorBox";
import type { CommunityReport, ReportType } from "@/lib/types";

const PRODUCT_TYPES: { value: ReportType; label: string }[] = [
  { value: "purchase", label: "Buying experience" },
  { value: "authenticity", label: "Genuine or fake" },
  { value: "delivery", label: "Delivery" },
  { value: "return", label: "Return" },
  { value: "refund", label: "Refund" },
];

const RETAILER_TYPES: { value: ReportType; label: string }[] = [
  { value: "purchase", label: "Buying experience" },
  { value: "delivery", label: "Delivery" },
  { value: "return", label: "Return" },
  { value: "refund", label: "Refund" },
  { value: "seller", label: "Seller behaviour" },
  { value: "authenticity", label: "Genuine or fake" },
];

function Stars({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          aria-checked={value === n}
          role="radio"
          className="p-0.5"
        >
          <Star className={`w-5 h-5 ${n <= value ? "text-amber-500 fill-current" : "text-muted-foreground/40"}`} />
        </button>
      ))}
    </div>
  );
}

/**
 * First-party purchase experiences — the one dataset BuyWise can own outright.
 *
 * Submissions are held for moderation before they appear, and merchants cannot pay
 * to add, remove or reorder them. Approved reports feed the Trust Engine.
 */
export default function CommunityReviews({
  productId,
  retailerId,
  subjectName,
}: {
  productId?: string;
  retailerId?: string;
  subjectName: string;
}) {
  const { user } = useAuth();
  const router = useRouter();
  const [reports, setReports] = useState<CommunityReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    report_type: "purchase" as ReportType,
    title: "",
    body: "",
    rating: 0,
    order_reference: "",
  });

  const types = productId ? PRODUCT_TYPES : RETAILER_TYPES;

  useEffect(() => {
    api
      .communityReports({ product_id: productId, retailer_id: retailerId })
      .then(setReports)
      .catch((e: ApiError) => {
        setError(e.message);
        setReports([]);
      });
  }, [productId, retailerId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) {
      router.push(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createCommunityReport({
        product_id: productId,
        retailer_id: retailerId,
        report_type: form.report_type,
        title: form.title.trim() || undefined,
        body: form.body.trim(),
        rating: form.rating || undefined,
        order_reference: form.order_reference.trim() || undefined,
      });
      setSubmitted(true);
      setOpen(false);
      setForm({ report_type: "purchase", title: "", body: "", rating: 0, order_reference: "" });
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const flag = async (id: string) => {
    if (!user) {
      router.push("/login");
      return;
    }
    const reason = window.prompt("Why should this be reviewed? (e.g. fake, abusive, promotional)");
    if (!reason) return;
    try {
      await api.flagCommunityReport(id, reason);
      setSubmitted(false);
      setError(null);
      alert("Reported. A moderator will look at it.");
    } catch (e) {
      setError((e as ApiError).message);
    }
  };

  return (
    <div className="glass rounded-2xl p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h3 className="font-semibold flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-indigo-500" /> BuyWise community experiences
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Real purchase experiences with {subjectName}, written by BuyWise users.
          </p>
        </div>
        <button
          onClick={() => (user ? setOpen(!open) : router.push(`/login?next=${encodeURIComponent(typeof window !== "undefined" ? window.location.pathname : "/")}`))}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium"
        >
          <MessageSquarePlus className="w-4 h-4" /> Write about your experience
        </button>
      </div>

      {submitted && (
        <div className="mb-4 p-3 rounded-xl bg-emerald-500/10 text-emerald-600 text-sm border border-emerald-500/20 flex gap-2">
          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          <span>
            Thanks — your experience was submitted. It appears publicly once a moderator has
            checked it, which is how BuyWise keeps merchants from planting reviews.
          </span>
        </div>
      )}
      {error && <ErrorBox message={error} className="mb-4" />}

      {open && (
        <form onSubmit={submit} className="mb-6 p-4 rounded-xl bg-muted/30 space-y-3">
          <div>
            <label className="text-sm font-medium mb-1.5 block">What is this about?</label>
            <div className="flex flex-wrap gap-2">
              {types.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => setForm({ ...form, report_type: t.value })}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    form.report_type === t.value
                      ? "border-indigo-500 bg-indigo-500/10 text-indigo-500"
                      : "border-border/40 hover:bg-muted"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium mb-1.5 block">Your rating</label>
            <Stars value={form.rating} onChange={(rating) => setForm({ ...form, rating })} />
          </div>

          <label className="block text-sm font-medium">
            Headline <span className="font-normal text-muted-foreground">(optional)</span>
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              maxLength={200}
              placeholder="Arrived two days late but genuine"
              className="mt-1 w-full px-4 py-2.5 rounded-xl bg-background/60 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm font-normal"
            />
          </label>

          <label className="block text-sm font-medium">
            What happened?
            <textarea
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
              required
              minLength={20}
              maxLength={4000}
              rows={4}
              placeholder="Describe what you ordered, how it arrived, and how any problems were handled."
              className="mt-1 w-full px-4 py-2.5 rounded-xl bg-background/60 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm font-normal"
            />
            <span className="text-xs text-muted-foreground">
              {form.body.trim().length}/20 characters minimum. No links or contact details.
            </span>
          </label>

          <label className="block text-sm font-medium">
            Order reference <span className="font-normal text-muted-foreground">(optional, for verification)</span>
            <input
              value={form.order_reference}
              onChange={(e) => setForm({ ...form, order_reference: e.target.value })}
              maxLength={100}
              placeholder="e.g. 408-1234567-1234567"
              className="mt-1 w-full px-4 py-2.5 rounded-xl bg-background/60 border border-border/40 outline-none focus:ring-2 focus:ring-indigo-500/30 text-sm font-normal"
            />
            <span className="text-xs text-muted-foreground">
              Stored only as a one-way hash so your experience can be marked verified. Never shown
              to anyone, including the retailer.
            </span>
          </label>

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy || form.body.trim().length < 20}
              className="px-4 py-2 rounded-xl gradient-primary text-white text-sm font-medium disabled:opacity-50"
            >
              {busy ? "Submitting…" : "Submit experience"}
            </button>
            <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-xl glass text-sm">
              Cancel
            </button>
          </div>
        </form>
      )}

      {reports === null && !error && <Spinner label="Loading experiences…" />}
      {reports && reports.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No community experiences yet. If you&apos;ve bought from {subjectName}, yours would be the
          first.
        </p>
      )}
      {reports && reports.length > 0 && (
        <ul className="space-y-3">
          {reports.map((r) => (
            <li key={r.id} className="p-4 rounded-xl bg-muted/30">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                {r.rating ? (
                  <span className="flex items-center gap-0.5 text-amber-500 text-sm font-medium">
                    <Star className="w-3.5 h-3.5 fill-current" />
                    {r.rating}
                  </span>
                ) : null}
                {r.title && <span className="font-medium text-sm">{r.title}</span>}
                {r.verification_status === "verified" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">
                    <ShieldCheck className="w-3 h-3" /> Verified purchase
                  </span>
                )}
                <span className="text-xs text-muted-foreground capitalize">
                  {r.report_type.replace("_", " ")}
                </span>
              </div>
              <p className="text-sm whitespace-pre-wrap">{r.body}</p>
              <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                <span>{r.username ?? "BuyWise user"}</span>
                <span>{formatRelativeTime(r.created_at)}</span>
                <button onClick={() => flag(r.id)} className="inline-flex items-center gap-1 hover:text-rose-500">
                  <Flag className="w-3 h-3" /> Report
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="text-xs text-muted-foreground mt-4">
        Experiences are moderated before publication and merchants cannot pay to add, remove or
        reorder them.{" "}
        {retailerId
          ? "Approved experiences become evidence in this retailer's Trust Score."
          : "These are experiences with this product and do not change any retailer's Trust Score."}
      </p>
    </div>
  );
}
