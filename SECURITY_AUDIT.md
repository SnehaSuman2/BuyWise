# BuyWise — Security Audit

Scope: backend (FastAPI), frontend (Next.js), configuration, payments. Status reflects the v2 codebase.

## Findings (before) and remediation

| Area | Before | Now |
|---|---|---|
| Secrets | Default `SECRET_KEY` accepted; keys documented only in README; `.env` ignored but `.env.*` not | Settings refuse insecure `SECRET_KEY`, SQLite or localhost URLs in `ENVIRONMENT=production`; dev generates an ephemeral key. `.gitignore` ignores `.env`, `.env.*`, `**/.env*` (keeps `.env.example`). Logger redacts configured secrets, bearer tokens, `api_key=` params, Razorpay/OpenAI key patterns. Only `NEXT_PUBLIC_*` reach the browser; `/meta` exposes Razorpay key *id* only. |
| Authentication | JWT ok; refresh tokens non-revocable; passlib/bcrypt version mismatch risk | bcrypt (cost 12) directly; password strength check; refresh tokens carry `jti`, stored hashed in `refresh_sessions`, **rotated on every refresh** and revoked on logout; `token_version` invalidates all access tokens on logout-all / password change / deletion. Login uses a constant-time-ish path (always runs a hash check). Google ID tokens verified server-side (audience, issuer, email_verified). |
| Authorization | No admin role enforcement; any user could not access others' alerts (ok) but admin routes absent | `get_admin_user` dependency; admin role only via `ADMIN_EMAILS`; alerts/saved products/payments/subscription queries always filter by `user_id`; account deletion requires typing `DELETE` + password. Tests cover cross-user isolation and admin protection. |
| Rate limiting | None | slowapi: default 120/min, search 30/min, agent 20/min, auth 10/min, payments 10–20/min, webhooks 120/min. Redis storage when available. Trusts `X-Forwarded-For` only in production behind a proxy. |
| Input validation | Loose | Pydantic constraints on every body/query (lengths, ranges, enums/regex). Search rejects empty input. |
| SSRF | User URL passed to providers unchecked | `validate_public_http_url`: http(s) only, rejects loopback/private/link-local/reserved/unspecified IPs, `localhost`, `.local/.internal/.lan/.home/.corp`, single-label hosts, >2048 chars. BuyWise never fetches user URLs directly; only the hostname/path are used to route to SerpApi. Uploaded images validated (magic bytes, ≤5MB). |
| SQL injection | ORM only | ORM only; no raw SQL string formatting. |
| XSS | Agent page used `dangerouslySetInnerHTML` on model output | Removed. `SafeText` renders bold/italics via React elements. JSON-LD is serialised with `JSON.stringify` from server data only. |
| CSRF | Bearer tokens (not cookies) | Unchanged model: bearer tokens in `Authorization` header; CORS restricts origins to the app URL + `CORS_ORIGINS`, methods to GET/POST/PATCH/DELETE, headers to Authorization/Content-Type. |
| Payments | None | Amount decided server-side from plan config; checkout signature HMAC-SHA256 with `hmac.compare_digest`; payment additionally fetched from Razorpay (status/amount/order) when reachable; webhook HMAC over the **raw body**; events deduped by `X-Razorpay-Event-Id` (unique constraint, duplicate → 200 `duplicate`); invalid signature → 400 and recorded; payload size capped at 512KB. Activation only after verification. Cross-user order verification returns 404 (tested). |
| Webhook replay/idempotency | — | `webhook_events (provider, event_id)` unique; `_mark_paid` idempotent. |
| Session storage | `localStorage` | Still `localStorage` (separate API origin makes httpOnly cookies impractical without a BFF). Mitigations: short access tokens (30 min), rotating refresh tokens, strict CSP (`script-src 'self'` + Google/Razorpay only), no `dangerouslySetInnerHTML`, `X-Frame-Options: DENY`. See TODO for the cookie/BFF upgrade. |
| Security headers | None | Backend: nosniff, DENY, referrer policy, `Cache-Control: no-store`, HSTS in production. Frontend: CSP, nosniff, DENY, Permissions-Policy, referrer policy, `poweredByHeader: false`. |
| Logging | Default | Redaction filter; email addresses masked in email logs; IPs stored only as salted hashes in `affiliate_clicks`; unhandled exceptions logged without request bodies; recent errors kept in memory for admin only. |
| Docs endpoint | Always on | `/docs` and `/redoc` disabled in production. |
| Seed data | Demo user `demo@buywise.ai / Demo@123` | Removed. Seeding refuses to run in production. |
| Uploads | — | Served from `/uploads` as static files with random names; only image types accepted. |
| Trust integrity | Scores hard-coded | Trust code cannot import commercial modules (AST test). Affiliate tags applied only at the redirect. |
| Dependencies | Invalid build backend | `pip install -e .` works; ruff clean; frontend `npm audit` not blocking (no known high-severity issues at install). |

## Remaining risks / recommendations

1. Move tokens to httpOnly cookies via a Next.js route-handler BFF (or same-site API domain) — medium priority.
2. Add email verification on sign-up (currently `is_verified` is true only for Google accounts).
3. Add CAPTCHA/turnstile on register/login if abuse appears (rate limits exist).
4. Rotate `SECRET_KEY` procedure: bump `token_version` for all users or accept re-login.
5. Run `pip-audit` / `npm audit` in CI; pin dependency versions before the first production deploy.
6. Put the API behind a reverse proxy with TLS and body-size limits; set `CORS_ORIGINS` explicitly.
7. Backups for Postgres; `webhook_events` and `payments` are the audit trail — never truncate.
