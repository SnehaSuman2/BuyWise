# BuyWise — API Integrations

Every integration is optional. Missing credentials → clearly labelled demo/disabled behaviour. Never put credentials in code or in `NEXT_PUBLIC_*` variables.

| Integration | Env vars | Mode when empty | Where to get it | Test |
|---|---|---|---|---|
| **SerpApi** (all engines) | `SERPAPI_API_KEY` | Demo catalog, banner shown | serpapi.com → Dashboard → "Your Private API Key" | `GET /api/v1/meta` → `data_mode: live`; search "Sony WH-1000XM5"; admin `/api/v1/admin/status` shows per-engine calls |
| **OpenAI** | `OPENAI_API_KEY`, `OPENAI_MODEL` | Template explanations, heuristic intent parsing | platform.openai.com → API keys | `/products/{id}/recommendations` → `ai_provider: openai`; agent answers are LLM-written |
| **PostgreSQL** | `DATABASE_URL`, `DIRECT_DATABASE_URL` | SQLite file (dev only; refused in production) | Any Postgres 16 (Neon, Supabase, RDS, Docker) | `alembic upgrade head` |
| **Redis** | `REDIS_URL` (+ optional `CELERY_*`) | In-memory cache; Celery unavailable → run `python -m app.workers.run_jobs` | Upstash, Redis Cloud, Docker | `/admin/status` → `cache.backend: redis` |
| **Razorpay** | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Pricing page shows plans; checkout disabled with a notice | dashboard.razorpay.com → Settings → API Keys (test mode first); Webhooks → add `https://<api>/api/v1/webhooks/razorpay`, events `payment.captured`, `payment.failed`, `order.paid`; copy the webhook secret | Pay with test card; `/api/v1/subscription` → `is_pro: true`; replay the webhook — second delivery returns `duplicate` |
| **Email (Resend)** | `EMAIL_API_KEY`, `EMAIL_FROM` | Console provider logs a masked line; notifications stored as `skipped` | resend.com → API Keys; verify your sending domain | Create an alert with a target above the current price → run `check_alerts` job → email arrives; dashboard shows `sent` |
| **Google Sign-In** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (backend), `NEXT_PUBLIC_GOOGLE_CLIENT_ID` (frontend, same id) | Button hidden | console.cloud.google.com → APIs & Services → Credentials → OAuth client (Web); authorised JS origins = your site URL | Button appears on /login; ID token verified at `/auth/google` |
| **Trustpilot** | `TRUSTPILOT_ENABLED=true`, `TRUSTPILOT_API_KEY`, optional `TRUSTPILOT_API_SECRET`, `TRUSTPILOT_ACCESS_TOKEN`, `TRUSTPILOT_BUSINESS_UNIT_ID` | Provider disabled; Trust Engine uses other evidence | Trustpilot Business account → API access | `/retailers/{id}/trust` evidence includes `source: trustpilot` |
| **Affiliate** | `AMAZON_AFFILIATE_TAG`, `FLIPKART_AFFILIATE_ID` | Plain product links | Amazon Associates (amazon.in), Flipkart Affiliate | `/api/v1/affiliate/disclosure` lists active programmes; `/go/{offer_id}` redirects with tag |

## SerpApi engines and routing

One key, `SerpApiClient.search(engine, params)`, cached by (engine, params). Engines (`app/providers/serpapi/`):

| Engine | Used for | Priority |
|---|---|---|
| `google_shopping` | Text search across Indian retailers | Phase 1 |
| `google_product` | Cross-retailer offers with base + shipping for a Google product id | Phase 1 (helper) |
| `amazon` (search) | Amazon.in fallback / retailer search | Phase 1 |
| `amazon_product` | ASIN → identifiers, specs, buybox, other sellers | Phase 1 |
| `google` (search) | Trust evidence queries: reviews, complaints, refund, delivery, scam, customer service | Phase 1 |
| `google_lens` | Image → visual matches | Phase 2 |
| `google_images` | Image results for a query | Phase 3 (off by default) |
| `bing_shopping` | Alternative shopping search | Phase 3 (off) |
| `google_reverse_image` | Pages containing an image | Phase 3 (off) |

Routing: text → Google Shopping (→ Bing if enabled) → Amazon Search only if fewer than 3 results. URL → Amazon Product for amazon.in, else slug → Google Shopping. Image → Lens → text search for prices. Trust → Google Search (6 cached queries per retailer, refreshed weekly by the `refresh_trust` job).

Reliability: 20s timeout, 2 retries with backoff on 429/5xx, "no results" treated as empty not error, per-engine stats (calls, cache hits, failures, rate-limited, latency) exposed at `/api/v1/admin/status`. Field parsing is tolerant (`extracted_price` or `price` strings, list or string `delivery`). Response shapes were modelled on SerpApi's documented payloads and covered by fixture tests; verify against live responses when the key is added and adjust `normalize_*` functions if a field name differs.

## AI provider abstraction

`providers/llm/base.py` → `OpenAIProvider` (HTTP, JSON mode) or `DemoLLMProvider`. The LLM is only used for: intent extraction, evidence classification refinement, review summarisation, and explanations of a structured payload. Prompts forbid inventing data; the deterministic engines remain the source of truth.

## Trust evidence providers

`TrustEvidenceProvider` implementations: `GoogleSearchEvidenceProvider`, `TrustpilotProvider` (optional), `DemoTrustEvidenceProvider`. Curated policy facts in `app/data/retailers.py` are added as `source_type=policy` evidence with source URLs.
