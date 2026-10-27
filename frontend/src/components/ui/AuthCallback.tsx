"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LoaderCircle, ShieldCheck } from "lucide-react";
import { completeSocialLogin } from "@/lib/oauth";
import { useAuth } from "@/lib/auth";

export default function AuthCallback() {
  const [error, setError] = useState("");
  const router = useRouter();
  const { refreshUser } = useAuth();
  useEffect(() => {
    let active = true;
    completeSocialLogin().then(async result => {
      await refreshUser();
      if (active) {
        sessionStorage.setItem("buywise:login-completed", result.provider);
        router.replace(result.next);
      }
    }).catch(e => { if (active) setError(e instanceof Error ? e.message : "Please try signing in again."); });
    return () => { active = false; };
  }, [router, refreshUser]);
  return <div className="max-w-md mx-auto px-6 py-24 text-center"><ShieldCheck className="mx-auto mb-5 text-indigo-500" size={40} /><h1 className="text-2xl font-bold">{error ? "Let’s try that again" : "Completing your sign-in"}</h1>{error ? <><p role="alert" className="my-5 text-muted-foreground">{error}</p><Link href="/login" className="inline-block px-6 py-3 rounded-xl bg-indigo-600 text-white">Back to sign in</Link></> : <p role="status" className="flex items-center justify-center gap-2 mt-5"><LoaderCircle size={18} className="animate-spin" />Taking you back to BuyWise…</p>}</div>;
}
