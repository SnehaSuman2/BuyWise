import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Terms of Service", description: "Terms for using BuyWise.", alternates: { canonical: "/terms" } };

export default function TermsPage() {
  return (
    <article className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2">Terms of Service</h1>
      <p className="text-sm text-muted-foreground mb-8">Last updated: 14 September 2026</p>
      <div className="space-y-6 text-sm leading-relaxed">
        <section><h2 className="font-semibold text-lg mb-2">1. The service</h2><p>BuyWise helps you compare offers, assess retailer trust and decide when to buy. BuyWise does not sell products. Purchases are made on retailer websites under their terms.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">2. Price accuracy disclaimer</h2><p>Prices, shipping charges, coupons, availability and delivery estimates are collected from retailers and third-party data providers at a point in time. They can change at any moment and may differ by pincode, seller, payment method or account. <strong>The final price is always the price shown at the retailer&apos;s checkout.</strong> Where BuyWise does not know a component (for example shipping), it says so rather than estimating it.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">3. Trust Scores and AI content</h2><p>Trust Scores are BuyWise&apos;s own opinion based on publicly available evidence, retailer-published policies and community reports, produced by the method described on the <Link href="/trust-methodology" className="text-indigo-500 hover:underline">Trust Score methodology</Link> page. They are not statements of fact about any business, are not endorsements, and may be incomplete or outdated. AI-generated explanations summarise BuyWise data and can contain errors. Always use your own judgement.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">4. Data sources</h2><p>Product and offer data comes from retailer listings and licensed data APIs; reputation evidence comes from public web sources and, where enabled, review platforms. When BuyWise runs without live data providers it shows clearly labelled demo data that must not be relied on.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">5. Affiliate links</h2><p>Some outbound links are affiliate links. See our <Link href="/affiliate-disclosure" className="text-indigo-500 hover:underline">affiliate disclosure</Link>. Commissions never influence Trust Scores, rankings or recommendations.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">6. Accounts and BuyWise Pro</h2><p>You must provide accurate information and keep your credentials secure. Pro subscriptions are billed through Razorpay for the period you select; access continues until the end of the paid period after cancellation. Refunds are handled case by case under applicable consumer law.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">7. Community content</h2><p>By submitting a purchase experience you confirm it is your genuine experience and grant BuyWise a licence to display it. We moderate submissions and remove content that is abusive, promotional, unlawful or appears manipulated. Merchants may not submit or solicit reviews of themselves.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">8. Acceptable use</h2><p>No scraping, automated bulk querying, attempts to circumvent rate limits, or interference with the service.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">9. Liability</h2><p>BuyWise is provided &quot;as is&quot;. To the extent permitted by law we are not liable for losses arising from reliance on prices, scores or recommendations, or from transactions with retailers.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">10. Governing law</h2><p>These terms are governed by the laws of India. Disputes are subject to the courts of the city where BuyWise is registered.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">11. Contact</h2><p>legal@buywise.co.in</p></section>
      </div>
    </article>
  );
}
