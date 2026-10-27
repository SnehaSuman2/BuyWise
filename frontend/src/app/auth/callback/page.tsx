import type { Metadata } from "next";
import AuthCallback from "@/components/ui/AuthCallback";
export const metadata: Metadata = { title: "Signing in", robots: { index: false, follow: false }, referrer: "no-referrer" };
export default function CallbackPage() { return <AuthCallback />; }
