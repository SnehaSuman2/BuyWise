# BuyWise — Project Audit

Audit date: 14 September 2026. This documents what existed before the v2 rebuild, what was wrong with it, and what was done.

## 1. What the project was

| Layer | Found | Status before |
|---|---|---|
| Frontend | Next.js 16 / React 19 / Tailwind 4 with a good glass-style design system, pages for home, search, product, retailer, agent, alerts, login/register | Every page read from `src/lib/mock-data.ts`. The API client (`api.ts`) existed but was never called. Login/register were simulated. Homepage displayed invented metrics ("2.4M+ products", "₹48Cr+ saved", "500K+ shoppers"). Footer links (Privacy, Terms, API Docs, GitHub) were dead `<span>`s. Agent page rendered model output with `dangerouslySetInnerHTML`. |
| Backend | FastAPI + async SQLAlchemy + Alembic + Celery skeleton; routes for auth, search, products, retailers, alerts, agent, community | Every provider was a demo stub (search, retailer offers, LLM). `SERP_API_KEY` existed in config but nothing used it. `alembic/versions` was empty (no migrations at all). Celery tasks were empty log statements. |
| Database | 14 models (users, products, variants, retailers, sellers, offers, price_history, reviews, review_analysis, trust_scores, trust_events, price_alerts, community_reports, searches) | Postgres-only column types; no migrations; no subscriptions/payments/webhooks/saved products/notifications/affiliate tables; no provenance on prices or trust. |
| Product matching | — | Did not exist. Search stored products by exact title equality. All offers were hard-coded `match_type="exact"`. |
| Price engine | `estimated_total = price + shipping - coupon` in the comparator | Shipping defaulted to 0 when unknown. Demo coupons were invented. |
| Price history | `PriceTracker` | **Fabricated** a random 90-day series whenever the DB had none, then produced BUY/WAIT signals from it. |
| Trust | `TrustScorer` | Hard-coded scores (Amazon 92, Flipkart 89 …) with prose "signals"; unknown retailers got 75. No evidence, no confidence model. |
| AI agent | `ShoppingAgent` | Called `DemoLLMProvider.parse_shopping_query()` which always returned "wireless mechanical keyboard under 5000" regardless of the query. |
| Auth | JWT + bcrypt (passlib) | Default `SECRET_KEY` string accepted silently; refresh tokens could not be revoked; no rate limiting (slowapi was a dependency but unused); no admin protection; demo user with a public password created by the seed. |
| Tests | 4 files | Only tested the demo providers and Pydantic schema construction. |
| Tooling | `pyproject.toml` | Invalid `build-backend = "setuptools.backends._legacy:_Backend"` — `pip install -e .` failed. |
| Repo | | The git repository root was `/Users/riya` (home directory), not the project. |

## 2. Real vs demo/mock (before)

Everything was demo. There was no path to live data even with an API key.

## 3. Broken / incomplete (before)

- No migrations → `alembic upgrade head` did nothing.
- Package would not install (`build-backend`).
- Frontend never talked to the backend; alerts page state was local only.
- `/alerts` create button did nothing; login always failed with a "demo mode" message.
- Agent page suggestion "MacBook vs Dell" was answered with canned text.

## 4. Security problems (before)

See `SECURITY_AUDIT.md`. Highlights: insecure default secret, CORS `allow_methods=["*"]`, no rate limits, `dangerouslySetInnerHTML`, no SSRF protection on URL input, refresh tokens non-revocable, no admin role enforcement, seeded credentials.

## 5. Duplicate / unnecessary code (before)

- Frontend `mock-data.ts` duplicated backend demo catalogs.
- `DemoRetailerProvider` and `DemoSearchProvider` overlapped; `price_comparator.py`, `price_tracker.py`, `trust_scorer.py`, `recommendation.py`, `search.py` were replaced by the new services.
- `PROJECT_PLAN.md` duplicated `ARCHITECTURE.md`/`TODO.md`.

## 6. What was reused

- The entire frontend design system (`globals.css`, glass cards, gradients, header/footer structure, animation classes).
- FastAPI/SQLAlchemy/Alembic/Celery stack and folder layout.
- Model names and table names (extended, not renamed).
- JWT/bcrypt approach (hardened).
- Demo catalog concept (rebuilt with variants so matching can be demonstrated honestly).

## 7. What changed (summary)

- **Providers**: `SerpApiClient` (one key, retries, cache, stats) + engines: Google Shopping, Google Product, Amazon Search, Amazon Product, Google Search, Google Lens, Google Images, Bing Shopping, Google Reverse Image. Demo providers behind the same interfaces. OpenAI provider (HTTP, no SDK). Optional Trustpilot. Resend email. Razorpay. Google ID-token verification.
- **Services**: product normalizer + matcher (EXACT / DIFFERENT_VARIANT / SIMILAR / UNKNOWN with confidence and reasons), true-price engine, price intelligence (stats + buy/wait with data-quantity confidence), evidence analyzer + Trust Engine (evidence → factors → score/risk/confidence/explanation), search orchestration (text/URL/image routing), offer comparison with picks, recommendation engine + grounded AI explanation, tool-based shopping agent, alerts with plan limits and background checker, notifications, Razorpay subscriptions with server-side verification and idempotent webhooks, affiliate redirect, account/dashboard/deletion, community moderation.
- **Database**: 24 tables, dialect-portable (Postgres in production, SQLite for local/tests), initial Alembic migration, provenance columns everywhere.
- **Frontend**: all pages wired to the API; mock data deleted; fake metrics removed; DEMO/LIVE badges; true-price breakdown; match badges; trust factors/concerns/evidence drawer; price chart; alerts; login/signup (+Google); dashboard; account; pricing with Razorpay checkout; privacy, terms, affiliate disclosure, trust methodology; sitemap, robots, metadata, JSON-LD; CSP headers.
- **Ops**: validated settings (fails in production with weak config), secret-redacting logger, rate limits, SSRF guard, admin diagnostics endpoint, job runs table, Celery beat schedule plus a no-Celery job runner, Docker prod build.
- **Tests**: 63 backend tests covering matching, pricing, history, trust, evidence analysis, SerpApi normalizers, Razorpay signatures + webhook idempotency, auth/authz, alerts, affiliate.
