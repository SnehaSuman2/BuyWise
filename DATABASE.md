# BuyWise — Database

PostgreSQL 16 in production (JSONB, UUID). The same models run on SQLite for local development and tests via portable types (`Uuid`, `JSON().with_variant(JSONB, "postgresql")`).

Migrations: `backend/alembic/versions/7532ab95d30a_initial_schema.py` (initial schema, 24 tables). Run `alembic upgrade head`. `alembic/env.py` reads the URL from settings (`DIRECT_DATABASE_URL` or `DATABASE_URL`).

## Tables

| Table | Purpose | Notable columns / constraints |
|---|---|---|
| `users` | Accounts | `email` unique, `username` unique, `password_hash` nullable (Google-only), `google_sub` unique, `role` (user/moderator/admin), `plan` (free/pro), `token_version` (global logout), `notification_preferences` JSON, `deleted_at` (soft delete) |
| `refresh_sessions` | Revocable refresh tokens | `token_hash` unique (sha256 of jti), `expires_at`, `revoked_at` |
| `saved_products` | Watchlist | unique (`user_id`,`product_id`) |
| `products` | Canonical products | identifiers `gtin`/`sku`/`mpn`/`asin` (indexed), `attributes` JSON (storage, ram, color, size…), `canonical_key` unique (dedup), `source_provider`, `source_url`, `is_demo` |
| `product_variants` | Variant rows | `storage`, `ram`, `color`, `size`, identifiers, `canonical_key` unique |
| `retailers` | Platforms | `slug` unique, `domain`, `is_marketplace`, `is_curated`, `policies` JSON (published policy facts + source URLs) |
| `sellers` | Marketplace merchants | unique (`retailer_id`,`name`), `rating`, `rating_count` |
| `offers` | One listing per product×retailer×seller×condition | true-price columns `listed_price`, `original_price`, `shipping_price` (nullable), `shipping_known`, `discount_amount`, `coupon_code/amount`, `estimated_final_price`, `final_price_known`; `match_type`, `match_confidence`, `match_reasons`; provenance `source_provider/engine`, `observed_at`, `is_demo` |
| `price_history` | Every observed price | `listed_price`, `shipping_price`, `estimated_final_price`, `source_provider/url`, `confidence`, `observed_at`, `is_demo`; indexes on (`product_id`,`observed_at`) and (`retailer_id`,`observed_at`) |
| `trust_evidence` | Analysed evidence | `source`, `source_type`, `url`, `topic`, `sentiment` (−1..1), `severity`, `confidence`, `extracted_claim`, `fingerprint` unique (dedupe), `published_at`, `collected_at`, `is_demo` |
| `trust_scores` | Score snapshots | `overall_score` nullable, `risk_level`, `confidence`, `confidence_level`, `factors`/`concerns`/`component_scores` JSON, `evidence_count`, `methodology_version`, `explanation`, `calculated_at`; `retailer_id` or `seller_id` |
| `trust_events` | Moderator-entered events | `event_type`, `source_url`, `weight` |
| `reviews`, `review_analysis` | Review intelligence | `source_url`, `provider`, `is_demo` |
| `price_alerts` | Alerts | `alert_type` (target_price / percent_drop), `target_price`, `drop_percent`, `baseline_price`, `trigger_count`, `last_checked_at`, `last_notified_at`, `deleted_at` |
| `notifications` | Delivery log | `kind`, `channel`, `status` (pending/sent/failed/skipped), `provider_message_id`, `error` |
| `subscriptions` | Pro plans | `plan`, `status`, `current_period_end`, `cancel_at_period_end` |
| `payments` | Razorpay orders | unique (`provider`,`provider_order_id`), `provider_payment_id` unique, `amount` (paise), `status`, `signature_verified`, `verified_via` (checkout/webhook), `raw` JSON (no secrets) |
| `webhook_events` | Idempotency + audit | unique (`provider`,`event_id`), `signature_valid`, `processed_at`, `processing_error` |
| `affiliate_clicks` | Outbound clicks | `destination_url`, `affiliate_applied`, `program`, `ip_hash` (hashed), `user_agent` |
| `searches` | Search log | `data_mode`, `providers_used`, `cache_hit`, `duration_ms`; anonymous rows purged after 30 days |
| `community_reports` | Purchase experiences | `report_type`, `order_reference_hash`, `verification_status`, `moderation_status`, `flag_count` |
| `report_flags` | Abuse flags | unique (`report_id`,`user_id`) |
| `job_runs` | Background job audit | `job_name`, `status`, `details` JSON, `error` |

All tables have UUID primary keys and `created_at`/`updated_at` where mutable. Foreign keys cascade where a child has no meaning without the parent (variants, offers, alerts, evidence) and `SET NULL` for audit rows (clicks, searches).

## Data-mode rules

- Demo rows carry `is_demo=true`. In live mode (`SERPAPI_API_KEY` set) price history, trust evidence and review analysis exclude demo rows; demo offers are superseded on the next live refresh.
- Only offers with `match_type='exact_match'` and confidence ≥ 0.7 produce `price_history` rows.

## Retention / cleanup (`cleanup` job)

Expired or revoked refresh sessions, anonymous searches older than 30 days, and job runs older than 30 days are deleted.
