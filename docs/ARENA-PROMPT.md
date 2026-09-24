# Prompt for an AI site builder (Arena, v0, Lovable, Bolt)

Copy everything below the line into the builder as your first message.

---

Build the customer-facing web app for **BuyWise**, a live shopping-intelligence
service for India. The backend already exists and is in production. You are
building the interface only. Never build or mock a backend.

## What BuyWise does

Shoppers in India cannot answer two questions before buying: what will this
actually cost me once shipping and coupons land, and can I trust this seller.
BuyWise answers both. It compares one product across every Indian retailer that
sells it, computes a true final price, and scores each seller's trustworthiness
from published policies and public evidence.

Revenue is a subscription paid by shoppers, never commission paid by merchants.
That is the product's whole position: it can afford to be honest about shops
because shops are not the customer.

## Absolute rules — breaking any of these makes the build worthless

1. **Never invent data.** No placeholder products, no sample prices, no fake
   reviews, no lorem ipsum product names, no made-up retailer names, no seeded
   "demo" catalogue. Every figure on screen must come from the live API. If an
   endpoint returns nothing, render an honest empty state saying so.
2. **Never fabricate a price, a rating, a review, a trust score or a price
   history point.** If a value is unknown, print "unknown" or omit it. Do not
   estimate, interpolate or round into precision the data does not have.
3. **Never present a similar product as an exact match.** The API labels match
   confidence; surface that label honestly.
4. **The server decides what a viewer may see.** The API withholds prices for
   users without a subscription and returns `locked: true`. Your UI only
   explains the lock. Never hide data client-side and call it a paywall, and
   never reveal something the server withheld.
5. **Refurbished and used items are never shown as new.** The API marks
   `condition`; display it.

## API

Base URL: `https://buywise-api-vaai.onrender.com/api/v1`

Auth is a JWT bearer token from `POST /auth/login`, kept in `localStorage`, sent
as `Authorization: Bearer <token>`. A 401 should trigger one refresh attempt via
`POST /auth/refresh`, then a redirect to login.

**Critical architectural constraint.** The token lives in the browser, so a
server-rendered page cannot read it. Any data whose response depends on the
viewer's subscription — prices, offers, price history, recommendations — **must
be fetched in the browser after mount**, never during server rendering.
Server-rendering those endpoints returns a withheld response for everyone,
including paying subscribers. Server-render only the product's name, images,
brand and specifications.

Endpoints you will need:

```
POST /search                       { query | url | image_base64, page_size, sort_by }
GET  /products/{id}                product detail
GET  /products/{id}/offers         every retailer's offer, ranked
GET  /products/{id}/history?days=  price observations + buy-or-wait signal
GET  /products/{id}/recommendations best overall / cheapest / safest picks
GET  /products/{id}/trust          trust scores for the sellers involved
GET  /products/{id}/reviews        aggregated review themes
GET  /products/family?line=        one product line, every size and store
GET  /catalog/{category}           curated models, filterable by specification
GET  /retailers  /retailers/{id}  /retailers/{id}/trust
GET  /subscription/plans           pricing tiers
GET  /subscription                 the viewer's plan
POST /payments/create              creates a Razorpay order
POST /payments/verify              server-side verification; only this activates
GET  /alerts  POST /alerts  DELETE /alerts/{id}
GET  /saved-products  POST /saved-products
POST /agent                        the AI shopping assistant
GET  /meta                         which integrations are live
```

Search responses may also carry `family` (one product line with its storage
sizes, colours and every store) and `catalog` (curated models matching a
category-style query such as "phone under 20000"). Render both when present.

## Pages

- **Home** — one search field accepting a product name, a retailer link, or a
  photo upload. Explain the two questions BuyWise answers. No fake product grid.
- **Search results** — product cards. When the response carries `family`, show
  the line's storage and colour choices above the cards with every store's price
  under the chosen variant, cheapest first. When it carries `catalog`, show spec
  filters (brand, RAM, storage, screen size, budget) inline in the results.
- **Product** — gallery of the real photographs the API returns, one per shop;
  lowest true final price; buy-or-wait signal; every retailer side by side with
  shipping, coupons and the estimated final total broken out; trust score per
  seller; price history with selectable windows from 7 days to 1 year; review
  themes; track-price and save buttons.
- **Product line** — the family view at `/family/{line}`.
- **Retailer** — trust score, the evidence behind it, and the published
  methodology.
- **Pricing** — plans from the API, never hardcoded. Razorpay Standard Checkout,
  UPI first, QR on desktop. Activation happens only after server verification.
- **Alerts**, **Saved products**, **Dashboard**, **Account**, **AI agent chat**,
  **Login/Signup**, plus Privacy, Terms, Affiliate disclosure, Trust methodology.

## Design

Audience is Indian shoppers aged 20 to 40, mostly on mobile. The feeling to aim
for is calm competence: this is a tool that tells you the truth about money, not
a marketplace shouting deals at you.

- Dark theme by default with a light mode toggle. Deep near-black background,
  indigo as the single accent, emerald reserved for good news such as a met
  price target or a high trust score, amber for warnings, rose for risk.
- Two typefaces at most. One geometric sans for headings, one neutral sans for
  text. Four or five sizes total, reused everywhere.
- Prices in Indian format with the rupee symbol and lakh grouping, tabular
  figures so columns align.
- Mobile first. The offer comparison must stay readable on a narrow screen;
  reflow it to cards rather than forcing a horizontal scroll.
- Loading states for every fetched section, never a blank page. The backend can
  be slow to wake, so show a waking-up banner with retry rather than an error.
- Accessible: 4.5:1 contrast, keyboard navigation everywhere, real button and
  link semantics, alt text, visible focus, and never colour alone to convey
  status.

## Technical

Next.js with the App Router, TypeScript, Tailwind. No component library that
imposes its own look. No state management library; React state and context are
enough. No analytics beyond a single measurement id from an environment
variable. Read the API base URL from `NEXT_PUBLIC_API_URL`. Put no secrets in
client code; the only public value is the Razorpay key id, which the API returns
when an order is created.

## Done means

Every page renders real data from the live API or an honest empty state. A
signed-in subscriber sees prices and history; a signed-out visitor sees the lock
and a clear reason to subscribe. Nothing anywhere is invented. The site is
usable on a phone, and readable with a keyboard and a screen reader.
