import type { Metadata } from "next";

export const metadata: Metadata = { title: "Affiliate Disclosure", description: "How BuyWise earns money and why it never affects Trust Scores.", alternates: { canonical: "/affiliate-disclosure" } };

export default function AffiliateDisclosurePage() {
  return (
    <article className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-6">Affiliate Disclosure</h1>
      <div className="space-y-5 text-sm leading-relaxed">
        <p>BuyWise may earn a commission when you buy something after clicking a retailer link on our site. This is how many comparison services are funded, and it costs you nothing extra.</p>
        <h2 className="font-semibold text-lg">What this does and does not affect</h2>
        <ul className="list-disc pl-5 space-y-1">
          <li>Commissions <strong>never</strong> change a retailer&apos;s Trust Score. The trust engine is built from evidence only and is architecturally separated from affiliate code.</li>
          <li>Commissions <strong>never</strong> change rankings or the BEST OVERALL, CHEAPEST, SAFEST, BEST VALUE and FASTEST picks. Those are computed from price, trust, delivery and match confidence only.</li>
          <li>Retailers cannot pay to appear, to be placed higher, or to remove concerns from their trust report.</li>
          <li>When a retailer has no affiliate programme we link to it exactly the same way.</li>
        </ul>
        <h2 className="font-semibold text-lg">How links work</h2>
        <p>Outbound links pass through a BuyWise redirect that records the click (with a hashed IP address) so we can detect abuse and attribute referrals. Links with an affiliate tag are marked with <code>rel=&quot;sponsored&quot;</code>.</p>
        <p className="text-muted-foreground">Programmes currently in use are listed by the API at <code>/api/v1/affiliate/disclosure</code> and will be updated as they change.</p>
      </div>
    </article>
  );
}
