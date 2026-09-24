# BuyWise — what it is, how it works, and how to rebuild its interface

Paste everything below the line into Manus as the first message.

---

You are rebuilding the customer-facing interface for **BuyWise**, a live
shopping-intelligence service for India at **https://www.buywise.co.in**.

**Start by using the live site yourself.** Search for a product, open a result,
open a retailer, read the pricing page. Everything described below is already
running, so treat the live site as the specification and this document as the
reasoning behind it. The backend exists and is in production. You are building
the interface only. Never build, mock or seed a backend.

---

## Part 1 — What BuyWise is

A shopper in India cannot answer two questions before buying online.

**What will this actually cost me?** The listed price is not the price. Shipping,
coupons and card offers move the total, and they only appear once you are deep in
someone's checkout. The cheapest listing is routinely not the cheapest purchase.

**Can I trust this seller?** On a marketplace the same product ships from sellers
with wildly different records. Nothing on the product page tells you which.

BuyWise answers both. It takes one product, finds every Indian retailer selling
it, computes what each will really charge, and scores how trustworthy each seller
is from published policies and public evidence.

**The business model is the product's spine.** BuyWise is paid by shoppers
through a subscription, never by merchants through commission. That is what makes
an honest Trust Score possible: a site funded by merchant commissions cannot
credibly rate the merchants paying it. In the codebase this is enforced rather
than promised, by an automated test that fails the build if commission or payment
data can reach the scoring engine.

Current scale: roughly 2,600 products, 4,900 live offers, 980 retailers seen,
8,600 dated price observations, 48 registered users, 42 active subscriptions.

---

## Part 2 — How it works, end to end

When someone searches, five things happen.

1. **Fetch.** Listings are pulled from shopping and retailer data sources scoped
   to the Indian market. Two independent suppliers are configured; the richer one
   is asked first and the second answers automatically if it returns nothing, so
   one supplier running out of credit is not an outage.
2. **Clean.** Accessories, rentals, spare parts, carrier services and catalogue
   listings naming a dozen models at once are removed before anything is shown.
   Prices far below the rest of the same model line are dropped as spam, judged
   only against other listings of that line rather than any fixed price table, so
   the rule works for products never seen before.
3. **Match.** Differently worded listings for the same item are grouped into one
   product. Refurbished and used items are never merged with sealed ones. A
   different storage size or colour stays a different product.
4. **Price.** For each offer, shipping, discounts and coupons are folded into a
   true final price, and the result is written down as a dated observation. Where
   a cost cannot be established it is recorded as unknown, never estimated.
5. **Rank.** Offers are ordered by that true final price, annotated with each
   seller's Trust Score, and returned as one comparison.

Alongside this, a curated registry of models holds real specifications entered
from manufacturer pages: screen, chip, RAM, storage options, camera, battery,
official colours. Prices never live in that registry. This is what lets a search
for a product line show every storage size the maker sells, even before a shop
has been seen selling one, and what powers specification filters.

Background jobs run on a schedule to refresh prices, check alerts, assess newly
seen retailers and clean up. Price history therefore accumulates day by day and
can never be back-filled, which the site states plainly.

---

## Part 3 — What people actually get

**Everyone, without paying:** search by product name, by pasting a retailer link,
or by uploading a photo; see which products exist and how many shops sell each;
read Trust Scores and buyer reviews; read the published scoring methodology; one
price alert; three saved products; thirty days of price history.

**Subscribers** additionally get: every retailer side by side with the true final
price broken into product price, shipping, discount and coupon; the best overall,
cheapest and safest picks with reasoning; full price history with windows from
seven days to a year and a buy-or-wait signal; many more alerts and saved
products; the AI shopping assistant.

Plans, which the interface reads from the API and never hardcodes: Free at zero,
Pro Monthly ₹99, Pro six months ₹449, Pro yearly ₹799. Nothing auto-renews; a
plan simply ends. Payment is Razorpay Standard Checkout, UPI first with a QR code
on desktop. A subscription activates only after the server verifies the payment
signature and re-checks the amount with Razorpay, never because the browser
reported success.

---

## Part 4 — How it should be designed

The audience is Indian shoppers between twenty and forty, mostly on a phone,
about to spend real money and wanting to stop worrying about it.

**The feeling to aim for is calm competence.** This is an instrument that tells
you the truth about money, not a marketplace shouting deals. Nothing flashes,
counts down or manufactures urgency. Restraint is the brand: a site that refuses
to invent a price should look like it refuses to invent anything.

**Structure.** Dark by default with a light mode. One deep near-black ground, one
indigo accent carrying every interactive element, emerald reserved strictly for
good news such as a met price target or a strong Trust Score, amber for caution,
rose for risk. Colour never carries meaning alone; every status also says so in
words.

**Type.** Two families at most, one geometric sans for headings and one neutral
sans for text, on a single scale of four or five sizes reused everywhere.
Emphasis comes from weight and colour, never a new size. Prices use Indian digit
grouping with the rupee symbol and tabular figures so columns align down a
comparison.

**Motion.** Sparing and physical. Content settles rather than flies. A number
that changes may count to its new value; little else animates without reason.
Every animation respects a reduced-motion preference and switches off entirely.
Hover effects never stand alone, because most visitors have no cursor.

**Layout.** Mobile first and genuinely so. The offer comparison is the hardest
screen in the product: on a narrow display it must reflow into cards rather than
forcing a horizontal scroll, and the true final price stays the largest thing in
each card. Tables are for wide screens only.

**Honesty as an interface principle.** Unknown shipping is labelled unknown, not
assumed free. A seller with thin evidence is shown as unrated, not given a
neutral score. A visual look-alike from a photo search is labelled a look-alike.
When live data is unavailable the page says what it is showing and why. These are
the product, not disclaimers to be tucked away.

**Loading and failure.** The backend sleeps when idle and can take a moment to
wake. Every fetched section needs a skeleton, and a slow start shows a calm
waking-up note with automatic retry rather than an error. A failed section never
blanks the page.

**Accessibility.** Contrast at least 4.5 to 1, full keyboard navigation, visible
focus, real button and link semantics, alt text on every image, dialogs that trap
focus and close on Escape.

---

## Part 5 — The build

### Absolute rules. Breaking any one makes the build worthless.

1. **Never invent data.** No placeholder products, no sample prices, no fake
   reviews, no made-up shop names, no seeded demo catalogue. Every figure comes
   from the live API. An endpoint returning nothing means an honest empty state.
2. **Never fabricate** a price, rating, review, Trust Score or history point. An
   unknown value prints as unknown. Do not estimate or interpolate.
3. **Never show a similar product as an exact match.** The API returns a match
   label and confidence; surface them.
4. **The server decides what a viewer may see.** It withholds prices for
   non-subscribers and returns `locked: true`. The interface only explains the
   lock. Never hide data client-side and call it a paywall, and never reveal
   anything the server withheld.
5. **Refurbished is never shown as new.** The API marks `condition`; display it.

### API

Base URL `https://buywise-api-vaai.onrender.com/api/v1`. Auth is a JWT bearer
token from `POST /auth/login`, held in `localStorage`. A 401 triggers one refresh
via `POST /auth/refresh`, then a redirect to login.

**An architectural constraint that has already caused one production bug.** The
token lives in the browser, so a server-rendered page cannot read it. Anything
whose response depends on the viewer's subscription — prices, offers, price
history, recommendations — **must be fetched in the browser after mount**.
Server-rendering those endpoints returns a withheld answer for everyone,
including paying subscribers. Server-render only name, images, brand and
specifications.

```
POST /search                        { query | url | image_base64, page_size, sort_by }
GET  /products/{id}                 detail
GET  /products/{id}/offers          every retailer, ranked by true final price
GET  /products/{id}/history?days=   observations + buy-or-wait signal
GET  /products/{id}/recommendations best overall / cheapest / safest
GET  /products/{id}/trust           seller scores
GET  /products/{id}/reviews         aggregated review themes
GET  /products/family?line=         one product line, every size and store
GET  /catalog/{category}            curated models, filterable by specification
GET  /retailers - /retailers/{id} - /retailers/{id}/trust
GET  /subscription - /subscription/plans
POST /payments/create - POST /payments/verify
GET/POST /alerts - DELETE /alerts/{id}
GET/POST /saved-products
POST /agent                         AI shopping assistant
GET  /meta                          which integrations are live
```

A search response may also carry `family` (a product line with its storage sizes,
colours and every store) and `catalog` (curated models matching a category query
such as "phone under 20000"). Render both when present.

### Pages

Home; search results; product; product line at `/family/{line}`; retailer;
pricing; alerts; saved products; dashboard; account; AI agent chat; login and
signup; privacy; terms; affiliate disclosure; trust methodology.

The product page is the centre of the product and deserves the most care: a
gallery of the real photographs the API returns, one per shop that sells the
item; the lowest true final price; the buy-or-wait signal; every retailer side by
side with the price broken down; Trust Score per seller; price history with
selectable windows; review themes; track-price and save.

### Technical

Next.js App Router, TypeScript, Tailwind. No component library that imposes its
own look. No state management library. Read the API base from
`NEXT_PUBLIC_API_URL`. No secrets in client code; the only public value is the
Razorpay key id, which the API returns when an order is created.

### Done means

Every page renders real data from the live API or an honest empty state. A
signed-in subscriber sees prices and history; a signed-out visitor sees the lock
and a clear reason to subscribe. Nothing anywhere is invented. It works on a
phone, with a keyboard, and with a screen reader.
