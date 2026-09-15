import Link from "next/link";
import { Sparkles } from "lucide-react";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const GITHUB = process.env.NEXT_PUBLIC_GITHUB_URL;

export default function Footer() {
  return (
    <footer className="border-t border-border/40 mt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <div className="w-7 h-7 rounded-lg gradient-primary flex items-center justify-center"><Sparkles className="w-4 h-4 text-white" /></div>
              <span className="text-lg font-bold bg-gradient-to-r from-indigo-500 to-purple-500 bg-clip-text text-transparent">BuyWise</span>
            </Link>
            <p className="text-sm text-muted-foreground">Compare prices. Check trust. Buy smarter.</p>
            <p className="text-xs text-muted-foreground mt-3">BuyWise finds the best place to buy — not just the cheapest.</p>
          </div>
          <div>
            <h4 className="font-semibold text-sm mb-3">Product</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link href="/" className="hover:text-foreground transition-colors">Search</Link></li>
              <li><Link href="/agent" className="hover:text-foreground transition-colors">AI Agent</Link></li>
              <li><Link href="/alerts" className="hover:text-foreground transition-colors">Price Alerts</Link></li>
              <li><Link href="/pricing" className="hover:text-foreground transition-colors">BuyWise Pro</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-sm mb-3">Trust &amp; Legal</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><Link href="/trust-methodology" className="hover:text-foreground transition-colors">Trust Score methodology</Link></li>
              <li><Link href="/affiliate-disclosure" className="hover:text-foreground transition-colors">Affiliate disclosure</Link></li>
              <li><Link href="/privacy" className="hover:text-foreground transition-colors">Privacy</Link></li>
              <li><Link href="/terms" className="hover:text-foreground transition-colors">Terms</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-sm mb-3">Developers</h4>
            <ul className="space-y-2 text-sm text-muted-foreground">
              <li><a href={`${API_URL}/docs`} target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">API Docs</a></li>
              {GITHUB && <li><a href={GITHUB} target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">GitHub</a></li>}
            </ul>
          </div>
        </div>
        <div className="mt-8 pt-8 border-t border-border/40 text-xs text-muted-foreground space-y-2">
          <p>Prices, shipping and availability are collected from retailers and third-party data providers and can change at checkout. Trust Scores are BuyWise&apos;s own assessment of publicly available evidence and are never influenced by payments, advertising or affiliate commissions.</p>
          <p>© {new Date().getFullYear()} BuyWise · AI Shopping Intelligence Platform · India</p>
        </div>
      </div>
    </footer>
  );
}
