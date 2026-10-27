# BuyWise V2: design, social sign-in and A/B testing

## What changed

V2 uses a quieter lavender palette, a clear search action, separate name/link/photo controls, static examples, an illustrative comparison card, three short steps, category entry points, a shopping-assistant entry point and expandable help. The preview is explicitly an illustration; it contains no invented offers, savings or testimonials.

The search and product pages add contextual progress and instructions for Variant B. Login/signup add Yahoo and Microsoft alongside existing Google and email, retain the intended return destination, and provide a guest-browsing link. Provider availability comes from the backend, so unavailable providers cannot be mistaken for working logins. Google’s public client ID can now come from that same endpoint.

HCI rationale: recognition through examples; fewer competing actions; progressive disclosure in FAQs; error recovery beside the search; visible progress; persistent labels; keyboard focus, skip navigation and reduced-motion support. Mobile styles stack content and preserve readable controls. These are design hypotheses, not proof of higher conversion: validate with users and the experiment.

The original homepage is preserved in `frontend/src/components/home/HomeV1.tsx`. Shared accessibility, authentication and analytics fixes apply to both arms; this is an experiment on the homepage and contextual shopping guidance, not an isolated test of login-provider choice.

## Preview and rollout

Run the existing frontend and backend as described in README.md, then open:

- `http://localhost:3000/?variant=b` — V2 preview.
- `http://localhost:3000/?variant=a` — original homepage preview.
- `http://localhost:3000/?variant=reset` — end preview mode in that tab.

Preview mode persists in session storage across navigation and excludes that tab from custom analytics and GA script loading on a fresh page load. Use direct URL loads to change preview mode. Browser storage being unavailable falls back to B and excludes the unstable assignment from measurement.

Default: `NEXT_PUBLIC_HOMEPAGE_EXPERIMENT=v2`, so all visitors see B.

For a randomized experiment, set `NEXT_PUBLIC_HOMEPAGE_EXPERIMENT=ab` in the frontend environment and rebuild/redeploy. New browsers get a 50/50 assignment, stored in local storage under `buywise:homepage_v2_2026_10`. Assignment is stable across visits, but clearing storage or using another browser creates a new assignment. For a new experiment, change `EXPERIMENT_ID`; do not reuse the ID after materially changing the treatment. Environment flags are compiled into the frontend build.

## Activate social sign-in

Backend variables (never NEXT_PUBLIC secrets):

```
YAHOO_CLIENT_ID=
YAHOO_CLIENT_SECRET=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
NEXT_PUBLIC_APP_URL=https://your-frontend-domain
```

Register the exact redirect URL with both providers:

```
https://your-frontend-domain/auth/callback
```

For Microsoft, register a **Web** redirect (the backend exchanges the code with a client secret), and allow personal Microsoft accounts plus organizational accounts if both are desired. Some organization administrators may restrict third-party sign-in. Request only `openid profile email`; no mail or contacts access is requested. For Yahoo, obtain an application with access to the requested OpenID scopes. Provider approval and account configuration must be completed in their developer consoles.

Run `cd backend && .venv/bin/alembic upgrade head` against the intended deployment database before using these routes. The new migration adds `oauth_identities` and `oauth_attempts`; it does not rewrite existing users. Existing deployments must deploy both backend and frontend. Local development startup creates the new tables automatically.

Google continues to use the existing Google Identity Services flow and `GOOGLE_CLIENT_ID`; its authorized JavaScript origin is the frontend domain. Email/password supports email addresses from any provider, including Yahoo and Outlook, independently of social login.

The new OAuth flows use expiring, one-use state stored as hashes in the database and a browser-held verifier; Microsoft also uses S256 PKCE. Token exchange and UserInfo retrieval occur on the backend at fixed provider endpoints. BuyWise session tokens are returned in the API body, never in redirect URLs. The callback clears authorization codes from browser history and is excluded from analytics and indexing.

Accounts are identified by provider + subject. Matching emails do **not** silently link accounts; existing users are directed to their original sign-in method. Provider profile emails do not confer administrator privileges. Microsoft accounts without an email claim cannot register through this flow; use email sign-up instead. Account linking is not included.

A real provider login still requires credentials and a manual end-to-end check on the registered domain. Automated tests mock external responses and do not claim to verify live provider configuration.

Provider references:
- [Yahoo Sign In](https://developer.yahoo.com/sign-in-with-yahoo/)
- [Yahoo OpenID Connect](https://developer.yahoo.com/oauth2/guide/openid_connect/)
- [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft UserInfo](https://learn.microsoft.com/en-us/entra/identity-platform/userinfo)

## Measure A/B results

Set `NEXT_PUBLIC_GA_MEASUREMENT_ID` and rebuild. No analytics are sent when it is empty. Register event-scoped custom dimensions `experiment_id`, `variant`, and `experiment_mode` in GA4. In the GA web stream, disable automatic enhanced page-view/history, site-search and form measurement so automatic collection does not duplicate the custom events or collect query strings. Use the custom events below.

Filter analysis to `experiment_id=homepage_v2_2026_10` and `experiment_mode=ab`. Exclude default-rollout (`v2`) data. Start each cohort with users who triggered `experiment_exposure`; people landing directly on a product must not enter the homepage denominator. Use unique users, not raw event counts, because revisits can emit multiple events.

| Event | Meaning |
| --- | --- |
| `experiment_exposure` | Homepage assigned and displayed |
| `search_started` | Homepage search submitted (text, link or photo) |
| `search` | Search response received; result count and data mode |
| `view_product` | Product page mounted, in either arm |
| `retailer_click` | Existing retailer outbound link clicked |
| `save_product` | Product successfully saved |
| `create_price_alert` | Price alert successfully created |
| `login_started` | Yahoo/Microsoft redirect requested |
| `login` / `sign_up` | Existing account events; Yahoo/Microsoft completion uses `login`, including first-time users |
| `help_opened` | V2 FAQ opened |

Suggested primary metric: percentage of exposed users who click through to a retailer during the session. Secondary metrics: search completion, product views, successful saves and alerts. Compare across device types and data mode; demo traffic is not evidence of real shopping conversion. Review errors and abandonment alongside conversion. Choose the duration and sample size before starting, hold prices/marketing/provider configuration stable across arms, and do not declare a winner from a handful of visits. This implementation instruments an experiment; it does not supply an automatic significance calculator or claim that V2 has already won.

Custom event payloads omit raw search text, full query strings, email addresses and authorization codes. GA uses its normal pseudonymous visitor/session identifiers. Local storage and provider identity processing are described on the Privacy page. Review the GA stream configuration before collecting live experiment data.

## Validation

```
cd frontend
npm run lint
npx tsc --noEmit
node --test tests/experiment.test.mjs
npm run build
# If Turbopack cannot create a worker in the local environment:
npm run build -- --webpack

cd ../backend
DEBUG=false .venv/bin/pytest tests/test_social_auth.py tests/test_auth_and_alerts.py -q
.venv/bin/ruff check app tests
```

Before launch, visually check 375px and desktop layouts, keyboard-only navigation, reduced motion, dark mode, empty/link/photo search errors, both preview arms, and the return destination after each live provider login. Browser-based visual QA was unavailable in the implementation session because computer-use permissions were not granted.


## Subscription conversion strategy (pre-deployment update)

The subscription catalogue now promotes only the three paid periods. Non-subscriber account entitlements remain internal; they are not a fourth plan card or a list of reasons to avoid upgrading.

The conversion sequence is **discover a product → encounter a relevant locked insight → compare paid plans → return to the product**. Search retains product recognition, specifications and matching. In the normal deployment (`PAYWALL_PRICES=true`), search and headline prices stay behind Pro. The product’s Compare offers section shows up to two eligible offers from other retailers as a free preview. All ranked retailers (including their duplicate listings), tied lowest prices, unavailable offers and non-exact matches are excluded from this preview. When no eligible preview exists, the page says so. Retailer rankings, recommendation winners, historical prices and buy/wait guidance always require an active Pro subscription, including when current-price previews are enabled. Basic trust evidence remains available.

Each locked panel names the benefit the user was trying to access: retailer prices/costs, best/cheapest/safest picks, or recorded trends and timing. Offer counts are real backend counts. The comparison panel places labelled, blurred skeletons for available pick categories above the visible preview rows. No hidden retailer names, prices or URLs are sent to the browser. Other panels use feature labels; no invented offers or savings are shown. A single clear upgrade action shows the entry plan’s actual price and duration. Paid plans retain visible total prices, durations and no-renewal terms.

`/subscription/plans` now returns paid plans only. History is withheld on both history URL aliases; basic accounts report zero history days. The assistant applies the same checks for text queries and direct product-ID requests. Guest comparison panels now fetch their actual locked state; an account upgrade or sign-out changes the client snapshot key so stale premium content is not retained in the UI.

Upgrade links carry the relevant product as `returnTo`; sign-in preserves the pricing destination, and a paid subscriber can return to the comparison. `pro_gate_view` measures a visible gate, `pro_upgrade_click` records which feature prompted the upgrade, `view_pro_plans` records the entry point, and existing `begin_checkout`/`purchase` events complete the funnel. Use the `feature` and `placement` event parameters to compare conversion from search, comparison, recommendations and history. Register them as event-scoped GA4 dimensions before analysis. Preview mode remains excluded from measurement.

This follows the [feature-gating approach described by RevenueCat](https://www.revenuecat.com/docs/playbooks/guides/freemium): show the product’s value and make the paid upgrade specific to the desired feature. Conversion uplift is a hypothesis to test; no improvement is claimed before user data exists. Hold the commercial policy identical in homepage A and B when comparing the two layouts.

Before deployment, explicitly set `PAYWALL_PRICES=true` in the backend environment. Run the entitlement, subscription, agent and payment tests plus the frontend build. Verify a real test-mode checkout and the return-to-product flow on the registered domain. Yahoo/Microsoft still require their previously documented provider credentials to activate.
