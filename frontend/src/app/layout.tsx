import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/layout/Header";
import Footer from "@/components/layout/Footer";
import DemoBanner from "@/components/layout/DemoBanner";
import { AuthProvider } from "@/lib/auth";
import { MetaProvider } from "@/lib/meta";

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(APP_URL),
  title: { default: "BuyWise — Compare prices. Check trust. Buy smarter.", template: "%s | BuyWise" },
  description: "BuyWise is an AI shopping decision engine for India: true price comparison across retailers, independent Trust Scores, price history and buy/wait signals.",
  keywords: ["price comparison", "trust score", "price history", "India", "Amazon", "Flipkart", "AI shopping"],
  openGraph: { type: "website", siteName: "BuyWise", title: "BuyWise — AI Shopping Intelligence", description: "Compare prices, check retailer trust and know when to buy.", url: APP_URL, locale: "en_IN" },
  twitter: { card: "summary_large_image", title: "BuyWise", description: "Compare prices. Check trust. Buy smarter." },
  robots: { index: true, follow: true },
  alternates: { canonical: "/" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN" suppressHydrationWarning>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <MetaProvider>
          <AuthProvider>
            <DemoBanner />
            <Header />
            <main className="min-h-[calc(100vh-4rem)]">{children}</main>
            <Footer />
          </AuthProvider>
        </MetaProvider>
      </body>
    </html>
  );
}
