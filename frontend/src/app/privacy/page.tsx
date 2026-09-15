import type { Metadata } from "next";

export const metadata: Metadata = { title: "Privacy Policy", description: "How BuyWise collects, uses and protects your data.", alternates: { canonical: "/privacy" } };

export default function PrivacyPage() {
  return (
    <article className="max-w-3xl mx-auto px-4 py-12 prose-sm">
      <h1 className="text-3xl font-bold mb-2">Privacy Policy</h1>
      <p className="text-sm text-muted-foreground mb-8">Last updated: 14 September 2026</p>
      <div className="space-y-6 text-sm leading-relaxed">
        <section><h2 className="font-semibold text-lg mb-2">1. Who we are</h2><p>BuyWise (&quot;we&quot;) operates www.buywise.co.in, an AI shopping decision engine for shoppers in India. This policy explains what we collect and why.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">2. What we collect</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>Account data</strong>: email address, username, display name and a salted password hash (or your Google account identifier if you sign in with Google). We never see your Google password.</li>
            <li><strong>Usage data</strong>: your searches, saved products and price alerts, so we can provide the service. Searches made while signed out are stored without any account link and deleted after 30 days.</li>
            <li><strong>Payment data</strong>: if you buy BuyWise Pro, Razorpay processes your payment. We store the order id, payment id, amount and status — never card or UPI details.</li>
            <li><strong>Outbound clicks</strong>: when you click through to a retailer we record the offer, a hashed (irreversible) IP address and your browser type to detect abuse and measure affiliate referrals.</li>
            <li><strong>Community reports</strong>: purchase experiences you choose to submit. Order references used for verification are stored only as one-way hashes.</li>
          </ul>
        </section>
        <section><h2 className="font-semibold text-lg mb-2">3. How we use it</h2><p>To run search, price tracking, alerts, trust analysis and subscriptions; to send the emails you asked for (price alerts, account notices); to keep the service secure; and to comply with the law. We do not sell personal data.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">4. Third-party processors</h2><p>We use search and product-data APIs (such as SerpApi), AI providers for explanations (product data only, never your account details), an email delivery provider, Razorpay for payments and hosting/database providers. Each processes data only to provide its service to us.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">5. Cookies and local storage</h2><p>We use browser local storage to keep you signed in and remember preferences such as dark mode. We do not use third-party advertising cookies.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">6. Retention and deletion</h2><p>You can delete your account from the Account page at any time. We anonymise your profile, remove saved products and alerts, and revoke all sessions immediately. Payment records are retained as required for accounting and tax purposes.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">7. Your rights</h2><p>You may access, correct or delete your data and withdraw consent to optional emails from the Account page or by contacting us at privacy@buywise.co.in. Residents of India have rights under the Digital Personal Data Protection Act, 2023.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">8. Security</h2><p>Passwords are hashed with bcrypt, API secrets are never exposed to the browser, connections are encrypted with TLS, and access to production systems is restricted.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">9. Changes</h2><p>We will post updates here and change the date above. Material changes will be announced in the app.</p></section>
        <section><h2 className="font-semibold text-lg mb-2">10. Contact</h2><p>privacy@buywise.co.in</p></section>
      </div>
    </article>
  );
}
