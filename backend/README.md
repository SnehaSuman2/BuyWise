---
title: BuyWise API
emoji: 🛍️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---

# BuyWise API

FastAPI backend for [BuyWise](https://www.buywise.co.in) — AI shopping intelligence for India. Compare true prices, check independent Trust Scores, track price history, get AI-grounded buy/wait recommendations.

Full source, architecture and setup docs live in the main repository: see `ARCHITECTURE.md`, `DATABASE.md`, `API_INTEGRATIONS.md` and `SECURITY_AUDIT.md` at the project root.

## Running this Space

This container runs the API only (`uvicorn app.main:app`). It requires these repository secrets to be set (Space Settings → Variables and secrets):

| Secret | Required | Notes |
|---|---|---|
| `ENVIRONMENT` | yes | `production` |
| `SECRET_KEY` | yes | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DATABASE_URL` | yes | External PostgreSQL (e.g. Neon/Supabase) — this Space's disk is ephemeral |
| `DIRECT_DATABASE_URL` | if using a pooled connection string | Neon/Supabase direct (non-pooled) URL, used by Alembic migrations |
| `NEXT_PUBLIC_APP_URL` | yes | Public URL of the deployed frontend |
| `API_PUBLIC_URL` | yes | This Space's own public URL (`https://<user>-<space>.hf.space`) |
| `CORS_ORIGINS` | recommended | Comma-separated extra allowed origins (e.g. a Vercel preview URL) |
| `SERPAPI_API_KEY`, `OPENAI_API_KEY`, `RAZORPAY_*`, `EMAIL_API_KEY`, `GOOGLE_CLIENT_*`, `TRUSTPILOT_*` | optional | Each integration runs in demo/disabled mode until set — see `API_INTEGRATIONS.md` |

Health check: `GET /health`. API docs are disabled in production (`ENVIRONMENT=production` turns off `/docs`).

No Celery worker runs in this Space (a Space is a single container). Background jobs (`refresh_prices`, `check_alerts`, `refresh_trust`, `cleanup`) can be triggered on a schedule from outside via `POST /api/v1/admin/jobs/{name}` (admin auth required), or run manually.
