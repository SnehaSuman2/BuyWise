# BuyWise — AI Shopping Intelligence

**Compare prices. Check trust. Buy smarter.** BuyWise finds the best place to buy — not just the cheapest.

BuyWise answers: *Where should I buy this? What is the real final price? Is this seller trustworthy? Is this the exact same product? Should I buy now or wait?*

- **True price comparison** — listed price + shipping − known coupons, with unknowns flagged instead of guessed.
- **Product matching** — GTIN / ASIN / MPN / model-code / variant matching. A 256GB phone is never matched with a 512GB one.
- **Independent Trust Engine** — 0–100 scores from public evidence, retailer policies and verified experiences, with factors, concerns and the evidence itself. Never influenced by payments or affiliate commissions.
- **Price history & buy/wait** — real recorded observations only; "Not enough BuyWise history yet" when data is thin.
- **AI shopping agent** — tool-based; the LLM explains structured results and never invents data.
- **Alerts, saved products, dashboard, BuyWise Pro (Razorpay)**, affiliate redirects with disclosure.

Demo mode runs without any API keys (clearly labelled). Live mode switches on automatically when credentials are added to `.env`.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Recharts |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 (async), Pydantic v2, Alembic |
| Database | PostgreSQL 16 (production) · SQLite (local dev / tests) |
| Cache / jobs | Redis + Celery (optional; in-memory cache and an inline job runner otherwise) |
| Data | SerpApi (one key: Google Shopping, Google Product, Amazon Search/Product, Google Search, Lens, Images, Bing Shopping, Reverse Image) |
| AI | OpenAI (pluggable `BaseLLMProvider`), demo fallback |
| Payments / email / auth | Razorpay · Resend · Google Sign-In |

## Quick start (no Docker, no keys)

```bash
# 1. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env          # edit later; empty keys = demo mode
python -m app.seed.demo_data        # creates SQLite tables + labelled demo data
uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local          # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000. API docs: http://localhost:8000/docs.

## Run with Docker (Postgres + Redis + Celery)

```bash
cp .env.example .env                # fill in what you have
docker compose up -d --build        # backend runs `alembic upgrade head` on start
docker compose exec backend python -m app.seed.demo_data   # optional demo catalog
```

Production images: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.

## Tests, lint, build

```bash
cd backend && .venv/bin/python -m pytest -q          # 63 tests (SQLite in-memory, no network)
cd backend && .venv/bin/ruff check app tests
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

## Background jobs

With Redis: `celery -A app.workers.celery_app worker` and `celery -A app.workers.celery_app beat` (schedule: prices every 6h, alerts every 30min, trust nightly, cleanup nightly).
Without Redis: `python -m app.workers.run_jobs refresh_prices check_alerts refresh_trust cleanup` (cron it), or `POST /api/v1/admin/jobs/{name}` as an admin.

## Environment variables

See `.env.example` (documented) and `API_INTEGRATIONS.md` for where each credential comes from and how to test it. Secrets never reach the browser; only `NEXT_PUBLIC_*` values do.

## Documentation

- `PROJECT_AUDIT.md` — what existed, what was wrong, what changed
- `ARCHITECTURE.md` — flows, layers, design rules
- `DATABASE.md` — schema and data-mode rules
- `API_INTEGRATIONS.md` — every external service, env vars, setup and tests
- `SECURITY_AUDIT.md` — findings and remaining risks
- `TODO.md` — prioritised remaining work

## API overview (`/api/v1`)

`GET /meta` · `POST|GET /search` · `GET /products/{id}` `/offers` `/history` `/trust` `/recommendations` `/reviews` · `GET /retailers` `/retailers/{id}` `/retailers/{id}/trust` `/retailers/sellers/{id}/trust` · `POST /agent` · `POST|GET /alerts`, `DELETE /alerts/{id}`, `/alerts/{id}/pause|resume` · `GET|PATCH|DELETE /account` · `GET /dashboard` · `POST|GET /saved-products`, `DELETE /saved-products/{product_id}` · `GET /subscription`, `/subscription/plans`, `POST /subscription/cancel` · `POST /payments/create`, `POST /payments/verify`, `GET /payments` · `POST /webhooks/razorpay` · `GET /go/{offer_id}` · `GET /affiliate/disclosure` · `POST|GET /community/reports`, `/community/reports/mine`, `/community/reports/{id}/flag` · `POST /auth/register|login|google|refresh|logout|logout-all|password`, `GET /auth/me`, `/auth/providers` · admin: `GET /admin/status`, `/admin/moderation`, `POST /admin/moderation/{id}`, `POST /admin/jobs/{name}`

## License

MIT
