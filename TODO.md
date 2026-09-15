# BuyWise — TODO (prioritised)

## P0 — needs your credentials (code is ready)
- [ ] Add `SERPAPI_API_KEY` → verify each engine's field names against live responses (`normalize_*` in `backend/app/providers/serpapi/`), run a few real searches, check `/api/v1/admin/status` costs.
- [ ] Add `OPENAI_API_KEY` → check intent extraction and explanations on real queries.
- [ ] Provision PostgreSQL + Redis, set `DATABASE_URL`/`REDIS_URL`, run `alembic upgrade head`, start Celery worker + beat.
- [ ] Razorpay test keys + webhook secret → run a test payment and a webhook replay.
- [ ] Resend API key + verified domain → send a real price alert email.
- [ ] Google OAuth client id/secret → test Google sign-in.
- [ ] Set `SECRET_KEY`, `ENVIRONMENT=production`, `NEXT_PUBLIC_APP_URL=https://www.buywise.co.in`, `API_PUBLIC_URL`, `CORS_ORIGINS`, `ADMIN_EMAILS`.

## P1 — product
- [ ] Pincode-aware offers (pass `location`/pincode to Google Shopping; store pincode on offers/observations).
- [ ] Email verification on sign-up; password reset flow (needs email provider).
- [ ] Community: UI for submitting purchase experiences and the moderation queue (API exists).
- [ ] Seller-level trust surfaced on offers when evidence exists (API exists: `/retailers/sellers/{id}/trust`).
- [ ] Review intelligence: import reviews from Amazon Product API (`reviews` in payload) into `reviews` table.
- [ ] Price-history backfill strategy: nightly `refresh_prices` for popular products, not only tracked ones (budget-controlled).
- [ ] Product page: variant switcher (list sibling variants from `same_product_different_variant` offers).

## P2 — platform
- [ ] httpOnly-cookie sessions via BFF; CSRF token for state-changing routes.
- [ ] Razorpay Subscriptions (recurring) instead of period passes; handle `subscription.*` events fully.
- [ ] Embedding-based similarity in the matcher (hook exists via `BaseLLMProvider.embed`).
- [ ] OpenTelemetry tracing / Sentry; CI pipeline (pytest, ruff, tsc, eslint, next build).
- [ ] Image upload storage on S3-compatible object storage instead of local `/uploads`.
- [ ] Admin UI page (frontend) for `/admin/status` and moderation.

## P3 — growth
- [ ] More retailers in `app/data/retailers.py` with verified policy links.
- [ ] Bing Shopping / Google Images / Reverse Image enabled once cost is understood.
- [ ] Trustpilot when API access is granted (`TRUSTPILOT_ENABLED=true`).
- [ ] ML-based trust/risk model trained on collected evidence + verified outcomes.
