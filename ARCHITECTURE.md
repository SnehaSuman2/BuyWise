# BuyWise — Architecture

```
                         BUYWISE FRONTEND (Next.js 16, App Router)
                                         │  HTTPS / JSON
                                         ▼
                          FastAPI backend  /api/v1  (rate-limited, CORS-locked)
        ┌──────────────────────┬──────────────────┬──────────────────┬──────────────────┐
        ▼                      ▼                  ▼                  ▼                  ▼
   Search layer           User layer         Payment layer     Trust layer        Jobs layer
   search_service         auth_service       subscription_svc  trust_service      workers/jobs
   offer_service          account_service    Razorpay client   evidence_analyzer  (Celery or inline)
   product_matcher        alert_service      webhooks          trust_engine
   price_engine           notification_svc
   price_intelligence
   recommendation_engine
   shopping_agent
        │                      │                  │                  │
        ▼                      ▼                  ▼                  ▼
   providers/registry ──► SerpApi engines | demo   PostgreSQL (SQLAlchemy async)   Redis (cache, Celery)
                          OpenAI | demo LLM        Alembic migrations
                          Trustpilot (optional)    24 tables, provenance on every fact
                          Resend | console email
```

## Request flows

**Text search** → `SearchService._search_text` → `GoogleShoppingProvider` (fallback Bing if enabled; Amazon Search only when <3 results) → `group_listings()` clusters listings with the matcher → `catalog.upsert_product/record_offer` (offers + price observations, only exact matches feed history) → results with DEMO/LIVE meta.

**URL search** → SSRF-validated → retailer detected from the registry → Amazon URL: `AmazonProductProvider` (ASIN → identifiers, buybox, other sellers) else slug-derived query → text search → every result carries a `match` vs the reference product.

**Image search** → `GoogleLensProvider` (needs a public image URL; uploads are stored under `/uploads` and require `API_PUBLIC_URL` to be reachable) → titles → text search for prices.

**Product page** → `/products/{id}` + `/offers` (refresh when stale, cost-aware) + `/history` (real observations only) + `/recommendations` (deterministic picks + AI explanation grounded in the payload) + `/trust` (per retailer).

**Trust** → `TrustService.ensure_retailer_score` (cached `CACHE_TTL_TRUST_SECONDS`) → policy evidence from `data/retailers.py` + Google Search evidence (6 queries, cached 7 days) + Trustpilot (optional) + approved community reports → `analyze_item` (topic/sentiment/severity/confidence, optional AI refinement) → `trust_engine.assess` → `TrustScore` + `TrustEvidence` rows.

**Agent** → `extract_intent` (heuristics, LLM if configured) → tools (search, recommendations, history, trust) → structured `AgentResponse` → explanation (LLM restricted to the facts payload, or template).

**Payments** → `/payments/create` (server decides amount) → Razorpay Checkout in browser → `/payments/verify` (HMAC signature + fetch payment from Razorpay) → activation. Webhook `/webhooks/razorpay` verifies raw-body HMAC, dedupes by event id, and can activate independently of the browser.

## Key design rules

1. **Provider abstraction** — `providers/base.py` defines `ProductSearchProvider`, `RetailerSearchProvider`, `ProductDetailsProvider`, `ImageSearchProvider`, `WebSearchProvider`, `TrustEvidenceProvider`. `providers/registry.py` chooses live vs demo from settings; downstream code never sees raw JSON.
2. **Normalized models** — `NormalizedListing`, `NormalizedProductDetails`, `EvidenceItem`, `ProviderResult` (ok/error/cached/is_demo) so failures degrade gracefully.
3. **Provenance** — offers and price observations store `source_provider`, `source_engine/url`, `observed_at`, `confidence`, `is_demo`. Trust evidence stores source, URL, date, confidence.
4. **Nothing invented** — unknown shipping/coupons stay unknown (`final_price_known=false`); history needs ≥7 daily observations over ≥7 days before a signal; trust reports "insufficient evidence" below the confidence threshold.
5. **Trust independence** — `trust_engine.py`, `evidence_analyzer.py`, `trust_service.py` cannot import affiliate/billing modules (enforced by `tests/test_trust_engine.py`). Affiliate tagging lives only in `affiliate_service.py` and the `/go/{offer_id}` redirect.
6. **Demo mode** — when `SERPAPI_API_KEY` is empty the demo providers run and every response carries `meta.data_mode="demo"`; the UI shows a banner and badges. Live and demo rows are never mixed silently (`is_demo` columns, live mode filters demo rows out of history/trust).
7. **Cost control** — SerpApi responses cached (search 6h, offers 3h, trust 7d); offers refreshed at most every `OFFER_REFRESH_SECONDS` per product; background jobs bounded per run; only tracked/saved products are refreshed by the scheduler.

## Directory map

```
backend/app
├── core/        config (validated), database (portable), security (JWT/bcrypt/refresh sessions), cache, http (SSRF guard, retries), logging (redaction), rate_limit
├── data/        retailers registry (curated policies), demo catalog
├── models/      SQLAlchemy models (see DATABASE.md)
├── providers/   base interfaces, registry, serpapi/*, demo/*, llm/*, trust/*, email/*, payments/razorpay, auth/google
├── services/    product_normalizer, product_matcher, price_engine, price_intelligence, evidence_analyzer, trust_engine,
│                catalog, search_service, offer_service, price_history_service, trust_service, recommendation_engine,
│                shopping_agent, alert_service, notification_service, subscription_service, affiliate_service,
│                account_service, community_service, auth_service, review_analyzer
├── api/v1/      meta, auth, search, products, retailers, agent, alerts, account, billing, affiliate, community, admin
├── workers/     jobs (async), celery_app, tasks, run_jobs (no-Celery runner)
├── seed/        demo_data
└── main.py
frontend/src
├── app/         pages (home, search, product/[id], retailer/[id], agent, alerts, login, signup, dashboard, account, pricing, privacy, terms, affiliate-disclosure, trust-methodology), sitemap, robots
├── components/  layout, ui (DataBadge, SafeText, GoogleSignInButton…), product (OffersTable, RecommendationCards, PriceHistoryChart, ProductActions), trust (TrustScoreCard)
└── lib/         api client (auth + refresh), types, auth/meta providers, theme, utils
```

## Deployment

- `docker compose up` → Postgres, Redis, backend (runs migrations), Celery worker + beat, frontend (dev).
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` → production images (Next standalone, uvicorn workers).
- Backend must be reachable at `NEXT_PUBLIC_API_URL` from browsers and at `API_INTERNAL_URL` from the Next server.
- Settings fail fast in `ENVIRONMENT=production` without a real `SECRET_KEY`, a Postgres `DATABASE_URL`, and a non-localhost `NEXT_PUBLIC_APP_URL`.
