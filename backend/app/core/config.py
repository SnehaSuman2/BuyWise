"""Application configuration.

All secrets come from environment variables (or a local .env file that is never
committed). Settings are validated at import time; anything that is unsafe for
production fails loudly when ENVIRONMENT=production.

Only settings that are *explicitly* meant for the browser live in the frontend
(NEXT_PUBLIC_*). Nothing in this file is ever sent to the client.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ROOT_DIR = _BACKEND_DIR.parent

# In tests, never read a developer's real .env file — a real secret sitting there
# (e.g. a live EMAIL_API_KEY) would otherwise make "demo mode" tests call real APIs.
# conftest.py sets ENVIRONMENT=test in the process environment before this module
# is first imported, so this check is reliable.
_ENV_FILES = (
    ()
    if os.environ.get("ENVIRONMENT") == "test"
    else (str(_ROOT_DIR / ".env"), str(_BACKEND_DIR / ".env"))
)

_INSECURE_SECRETS = {
    "",
    "change-me",
    "change-me-to-a-random-64-char-string",
    "change-me-to-a-random-64-char-string-in-production",
    "secret",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        # Root .env first, backend/.env overrides. Neither file is committed.
        # Empty in tests (see _ENV_FILES above) so tests are hermetic regardless
        # of what real secrets exist in a developer's local .env.
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "BuyWise"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    NEXT_PUBLIC_APP_URL: str = "http://localhost:3000"
    API_PUBLIC_URL: str = "http://localhost:8000"
    # Comma-separated list of extra allowed CORS origins.
    CORS_ORIGINS: str = ""

    # --- Database ---
    # Async URL used by the application. Postgres in production; SQLite works for local dev/tests.
    DATABASE_URL: str = "sqlite+aiosqlite:///./buywise.db"
    # Sync/direct URL used by Alembic migrations (and pooled-vs-direct setups such as Neon/Supabase).
    DIRECT_DATABASE_URL: str = ""

    # --- Redis / cache / jobs ---
    REDIS_URL: str = ""
    CACHE_TTL_SEARCH_SECONDS: int = 6 * 60 * 60
    CACHE_TTL_OFFERS_SECONDS: int = 3 * 60 * 60
    CACHE_TTL_TRUST_SECONDS: int = 7 * 24 * 60 * 60
    OFFER_REFRESH_SECONDS: int = 6 * 60 * 60
    # A product with fewer than two offers is refreshed sooner: one offer is not a comparison.
    OFFER_THIN_REFRESH_SECONDS: int = 30 * 60

    # --- Security ---
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    RATE_LIMIT_DEFAULT: str = "120/minute"
    RATE_LIMIT_SEARCH: str = "30/minute"
    RATE_LIMIT_AGENT: str = "20/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    ADMIN_EMAILS: str = ""  # comma-separated emails auto-granted the admin role

    # --- Market ---
    # BuyWise serves India. Google Shopping returns international merchants even with
    # gl=in; their prices are currency conversions a shopper here cannot actually pay.
    MARKET_FILTER_ENABLED: bool = True
    # Google Shopping identifies merchants by display name only (no URL), so most
    # legitimate Indian long-tail sellers are unrecognisable. Strict mode drops those
    # too, which in testing removed ~37 of 40 real listings. Default keeps unknowns and
    # drops only merchants identifiably outside India. Set true for maximum purity.
    STRICT_MARKET_FILTER: bool = False

    # --- Search data vendor (ONE key for every engine) ---
    # Either SerpApi or SearchApi supplies Google Shopping, Amazon, Google web search
    # and Google Lens. Configure one key; with both present, SEARCH_PROVIDER decides
    # ("auto" prefers SearchApi, whose plans are cheaper per search).
    SEARCHAPI_API_KEY: str = ""
    SEARCH_PROVIDER: Literal["auto", "serpapi", "searchapi"] = "auto"
    # After a quota or credential failure, stop calling the vendor for this long and
    # answer from the catalogue instead of making every shopper wait on retries.
    SEARCH_API_COOLDOWN_SECONDS: int = 15 * 60
    # "auto" keeps third-party responses in the database (shared, restart-proof) or
    # Redis when configured; "memory" is per process and mainly for tests.
    CACHE_BACKEND: Literal["auto", "memory"] = "auto"
    # Shared secret for the scheduled-job endpoint (/internal/jobs). Empty disables it.
    CRON_SECRET: str = ""
    # Per-run budgets for background work, so a scheduler cannot burn the search quota.
    PRICE_REFRESH_BATCH: int = 10
    TRUST_ASSESS_BATCH: int = 2
    # Set automatically by Render for web services; used when API_PUBLIC_URL is unset.
    RENDER_EXTERNAL_URL: str = ""

    SERPAPI_API_KEY: str = ""
    SERPAPI_TIMEOUT_SECONDS: float = 20.0
    SERPAPI_MAX_RETRIES: int = 2
    SERPAPI_COUNTRY: str = "in"
    SERPAPI_LANGUAGE: str = "en"
    SERPAPI_AMAZON_DOMAIN: str = "amazon.in"
    # Feature flags per engine (all share SERPAPI_API_KEY)
    SERPAPI_ENABLE_GOOGLE_SHOPPING: bool = True
    SERPAPI_ENABLE_GOOGLE_PRODUCT: bool = True
    SERPAPI_ENABLE_AMAZON_SEARCH: bool = True
    SERPAPI_ENABLE_AMAZON_PRODUCT: bool = True
    SERPAPI_ENABLE_GOOGLE_SEARCH: bool = True
    SERPAPI_ENABLE_GOOGLE_LENS: bool = True
    SERPAPI_ENABLE_GOOGLE_IMAGES: bool = False
    SERPAPI_ENABLE_BING_SHOPPING: bool = False
    SERPAPI_ENABLE_GOOGLE_REVERSE_IMAGE: bool = False

    # --- AI ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    GEMINI_API_KEY: str = ""
    # Google retires Gemini model versions periodically — a retired name fails with
    # HTTP 404 naming its replacement. Override via env without a code change.
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-001"
    # auto picks whichever key is configured, preferring Gemini (it has a free tier).
    AI_PROVIDER: Literal["auto", "openai", "gemini", "demo"] = "auto"

    # --- Razorpay ---
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    PRO_MONTHLY_PRICE_INR: int = 199
    PRO_YEARLY_PRICE_INR: int = 1499

    # --- Email ---
    EMAIL_PROVIDER: Literal["auto", "resend", "console"] = "auto"
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = "BuyWise <alerts@buywise.co.in>"

    # --- Google auth ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # --- Trustpilot (optional evidence source) ---
    TRUSTPILOT_ENABLED: bool = False
    TRUSTPILOT_API_KEY: str = ""
    TRUSTPILOT_API_SECRET: str = ""
    TRUSTPILOT_ACCESS_TOKEN: str = ""
    TRUSTPILOT_BUSINESS_UNIT_ID: str = ""

    # --- Affiliate (never influences trust or ranking) ---
    AMAZON_AFFILIATE_TAG: str = ""
    FLIPKART_AFFILIATE_ID: str = ""

    # --- Celery ---
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # --- Plan limits ---
    FREE_MAX_ALERTS: int = 3
    FREE_MAX_SAVED_PRODUCTS: int = 10
    PRO_MAX_ALERTS: int = 100
    PRO_MAX_SAVED_PRODUCTS: int = 500
    FREE_HISTORY_DAYS: int = 30
    PRO_HISTORY_DAYS: int = 365

    # ------------------------------------------------------------------ validators
    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.SECRET_KEY in _INSECURE_SECRETS:
            if self.ENVIRONMENT == "production":
                raise ValueError(
                    "SECRET_KEY must be set to a long random value in production "
                    '(e.g. `python -c "import secrets; print(secrets.token_urlsafe(64))"`).'
                )
            # Ephemeral key for dev/test: tokens are invalidated on restart, which is safe.
            object.__setattr__(self, "SECRET_KEY", secrets.token_urlsafe(48))
        if self.ENVIRONMENT == "production":
            if self.DATABASE_URL.startswith("sqlite"):
                raise ValueError(
                    "SQLite is not supported in production; set DATABASE_URL to PostgreSQL."
                )
            if self.NEXT_PUBLIC_APP_URL.startswith("http://localhost"):
                raise ValueError("NEXT_PUBLIC_APP_URL must be the public site URL in production.")
        if (self.RAZORPAY_KEY_ID and not self.RAZORPAY_KEY_SECRET) or (
            self.RAZORPAY_KEY_SECRET and not self.RAZORPAY_KEY_ID
        ):
            raise ValueError("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set together.")
        return self

    # ------------------------------------------------------------------ derived
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def active_search_provider(self) -> str:
        if self.SEARCH_PROVIDER in ("serpapi", "searchapi"):
            return self.SEARCH_PROVIDER
        return "searchapi" if self.SEARCHAPI_API_KEY else "serpapi"

    @property
    def search_api_enabled(self) -> bool:
        if self.active_search_provider == "searchapi":
            return bool(self.SEARCHAPI_API_KEY)
        return bool(self.SERPAPI_API_KEY)

    @property
    def serpapi_enabled(self) -> bool:
        """Kept for older call sites: true when any search vendor is configured."""
        return self.search_api_enabled

    @property
    def api_public_url(self) -> str:
        """Public base URL of this API, used for links and uploaded images.

        Falls back to the URL Render assigns when API_PUBLIC_URL was left at its
        localhost default, so photo search works on Render without extra setup.
        """
        url = self.API_PUBLIC_URL.rstrip("/")
        if url.startswith(("http://localhost", "http://127.")) and self.RENDER_EXTERNAL_URL:
            return self.RENDER_EXTERNAL_URL.rstrip("/")
        return url

    @property
    def openai_enabled(self) -> bool:
        return bool(self.OPENAI_API_KEY) and self.AI_PROVIDER in ("auto", "openai")

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.GEMINI_API_KEY) and self.AI_PROVIDER in ("auto", "gemini")

    @property
    def ai_enabled(self) -> bool:
        return self.gemini_enabled or self.openai_enabled

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.RAZORPAY_KEY_ID and self.RAZORPAY_KEY_SECRET)

    @property
    def razorpay_webhooks_enabled(self) -> bool:
        return bool(self.RAZORPAY_WEBHOOK_SECRET)

    @property
    def email_enabled(self) -> bool:
        return bool(self.EMAIL_API_KEY) and self.EMAIL_PROVIDER in ("auto", "resend")

    @property
    def google_auth_enabled(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID)

    @property
    def trustpilot_enabled(self) -> bool:
        return self.TRUSTPILOT_ENABLED and bool(self.TRUSTPILOT_API_KEY)

    @property
    def redis_enabled(self) -> bool:
        return bool(self.REDIS_URL)

    @property
    def demo_mode(self) -> bool:
        """True when product/offer data comes from simulated providers."""
        return not self.serpapi_enabled

    @property
    def data_mode(self) -> str:
        return "live" if self.serpapi_enabled else "demo"

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL or "memory://"

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL or "cache+memory://"

    @property
    def sync_database_url(self) -> str:
        """Sync driver URL for Alembic and Celery workers."""
        url = self.DIRECT_DATABASE_URL or self.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        return url

    @property
    def async_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("sqlite://") and "aiosqlite" not in url:
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url

    @property
    def cors_origins(self) -> list[str]:
        origins = {self.NEXT_PUBLIC_APP_URL.rstrip("/")}
        if not self.is_production:
            origins.update({"http://localhost:3000", "http://127.0.0.1:3000"})
        for o in self.CORS_ORIGINS.split(","):
            if o.strip():
                origins.add(o.strip().rstrip("/"))
        return sorted(origins)

    @property
    def admin_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip()}

    def integration_status(self) -> dict[str, dict]:
        """Non-secret summary of which integrations are live vs mock."""
        return {
            "search_api": {
                "mode": "live" if self.search_api_enabled else "mock",
                "configured": self.search_api_enabled,
                "provider": self.active_search_provider if self.search_api_enabled else "demo",
            },
            "ai": {
                "mode": "live" if self.ai_enabled else "mock",
                "configured": self.ai_enabled,
                "provider": "gemini"
                if self.gemini_enabled
                else ("openai" if self.openai_enabled else "demo"),
            },
            "razorpay": {
                "mode": "live" if self.razorpay_enabled else "mock",
                "configured": self.razorpay_enabled,
                "webhooks": self.razorpay_webhooks_enabled,
            },
            "email": {
                "mode": "live" if self.email_enabled else "console",
                "configured": self.email_enabled,
            },
            "google_auth": {
                "mode": "live" if self.google_auth_enabled else "disabled",
                "configured": self.google_auth_enabled,
            },
            "trustpilot": {
                "mode": "live" if self.trustpilot_enabled else "disabled",
                "configured": self.trustpilot_enabled,
            },
            "redis": {
                "mode": "redis" if self.redis_enabled else "memory",
                "configured": self.redis_enabled,
            },
            "database": {"mode": "postgresql" if "postgres" in self.DATABASE_URL else "sqlite"},
        }


@lru_cache
def get_settings() -> Settings:
    """Cache and return application settings."""
    return Settings()
