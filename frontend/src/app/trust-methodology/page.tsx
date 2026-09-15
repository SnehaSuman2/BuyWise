import type { Metadata } from "next";

export const metadata: Metadata = { title: "Trust Score Methodology", description: "How BuyWise calculates retailer and seller Trust Scores.", alternates: { canonical: "/trust-methodology" } };

export default function TrustMethodologyPage() {
  return (
    <article className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2">How BuyWise Trust Scores work</h1>
      <p className="text-sm text-muted-foreground mb-8">Methodology version 1.0</p>
      <div className="space-y-6 text-sm leading-relaxed">
        <section><h2 className="font-semibold text-lg mb-2">The pipeline</h2><p>Retailer or seller → evidence collection → evidence analysis → Trust Engine → score (0–100), risk level and confidence → explanation with the supporting evidence.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">Evidence sources</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>Retailer-published policies</strong>: return windows, buyer protection, cash on delivery, grievance contacts — recorded with source links and a review date.</li>
            <li><strong>Public web evidence</strong>: search results about reviews, complaints, refunds, delivery, customer service and fraud reports. Each result is classified by topic, sentiment and severity, and weighted by the reliability of its source. A page that merely contains the word &quot;scam&quot; is not treated as evidence of a scam.</li>
            <li><strong>Review platforms</strong> (optional, e.g. Trustpilot via its official API) when configured.</li>
            <li><strong>BuyWise community reports</strong>: moderated purchase experiences; verified purchases carry more weight.</li>
          </ul>
        </section>
        <section><h2 className="font-semibold text-lg mb-2">Scoring</h2><p>Evidence is grouped into factors — returns &amp; refunds, delivery reliability, customer service, product authenticity, fraud &amp; complaint patterns, business transparency and payment security. Each factor score is a weighted average of evidence sentiment, where weight = source reliability × analysis confidence × recency. Negative evidence is amplified by its severity. The overall score is a weighted mean of the factors; strong, corroborated fraud evidence caps the score.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">Confidence and risk</h2><p>Confidence reflects how much evidence exists, how many independent sources agree and how many factors are covered. With little evidence BuyWise reports <em>&quot;Insufficient evidence to confidently assess this retailer&quot;</em> instead of a risk verdict. Risk levels: 75+ low, 55–74 medium, below 55 higher risk based on available evidence.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">Independence</h2><p>No commercial input reaches the Trust Engine. It has no access to affiliate, advertising or subscription data, and this separation is enforced by automated tests. Retailers cannot pay to change a score.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">Wording</h2><p>BuyWise never states that a business is a scam. Scores describe the balance of available evidence and are refreshed periodically. If you believe a score is wrong, submit a purchase experience or contact trust@buywise.co.in.</p></section>
      </div>
    </article>
  );
}
