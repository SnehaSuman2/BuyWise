"""One HTTP client for whichever search-data vendor is configured.

BuyWise needs Google Shopping, Amazon search and product pages, Google web search
(trust evidence) and Google Lens (photo search). Two vendors expose all of those
through an API with the same shape of call, an engine name plus query parameters
with JSON back:

  * SerpApi    https://serpapi.com/search.json
  * SearchApi  https://www.searchapi.io/api/v1/search

They differ in a handful of parameter and field names, which each engine module
handles next to its normaliser. Everything else lives here once: the key, the
timeouts and retries, the response cache, quota handling, the circuit breaker and
per-engine statistics.

Why the circuit breaker: when the vendor's monthly quota ran out, every search
still fired two requests, each retried with back-off, and a shopper waited over a
minute to be shown nothing. Once a quota or credential failure is seen, further
calls fail instantly for a cool-down period and the search layer can fall back to
what the catalogue already knows.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.core.cache import cache
from app.core.config import get_settings
from app.core.http import request_with_retry

logger = logging.getLogger(__name__)

VENDORS: dict[str, dict[str, Any]] = {
    "serpapi": {"url": "https://serpapi.com/search.json", "extra": {"output": "json"}},
    "searchapi": {"url": "https://www.searchapi.io/api/v1/search", "extra": {}},
}

STATS: dict[str, dict[str, Any]] = {}
BREAKER: dict[str, Any] = {"open_until": 0.0, "reason": None, "opened_at": None}

_QUOTA_MARKERS = (
    "exhaust",
    "run out",
    "ran out",
    "quota",
    "limit reached",
    "search limit",
    "plan limit",
    "no credits",
    "insufficient credits",
    "upgrade your plan",
    "out of credits",
)


def _stat(engine: str) -> dict[str, Any]:
    return STATS.setdefault(
        engine,
        {
            "calls": 0,
            "cache_hits": 0,
            "failures": 0,
            "rate_limited": 0,
            "short_circuited": 0,
            "total_latency_ms": 0,
            "last_error": None,
        },
    )


class SearchApiError(Exception):
    """Base error for search-vendor failures."""


class SearchApiAuthError(SearchApiError):
    pass


class SearchApiRateLimited(SearchApiError):
    pass


class SearchApiQuotaExceeded(SearchApiError):
    """The vendor account has no searches left. Retrying will not help."""


def breaker_open() -> bool:
    return BREAKER["open_until"] > time.time()


def breaker_status() -> dict[str, Any]:
    open_ = breaker_open()
    return {
        "open": open_,
        "reason": BREAKER["reason"] if open_ else None,
        "retry_in_seconds": max(0, int(BREAKER["open_until"] - time.time())) if open_ else 0,
    }


def _open_breaker(reason: str, seconds: float) -> None:
    BREAKER["open_until"] = time.time() + seconds
    BREAKER["reason"] = reason
    BREAKER["opened_at"] = time.time()
    logger.warning("Search API circuit opened for %ds: %s", int(seconds), reason)


def reset_breaker() -> None:
    BREAKER.update({"open_until": 0.0, "reason": None, "opened_at": None})


class SearchClient:
    def __init__(self, provider: str, api_key: str) -> None:
        if provider not in VENDORS:
            raise ValueError(f"Unknown search vendor {provider!r}")
        settings = get_settings()
        self.provider = provider
        self.api_key = api_key
        self.base_url = VENDORS[provider]["url"]
        self._extra = VENDORS[provider]["extra"]
        self.timeout = settings.SERPAPI_TIMEOUT_SECONDS
        self.max_retries = settings.SERPAPI_MAX_RETRIES
        self.cooldown = settings.SEARCH_API_COOLDOWN_SECONDS

    @property
    def name(self) -> str:
        return self.provider

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search(
        self, engine: str, params: dict[str, Any], *, cache_ttl: int = 3600
    ) -> dict[str, Any]:
        if not self.enabled:
            raise SearchApiAuthError("No search API key is configured")
        stat = _stat(engine)
        clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
        # The cache key ignores the vendor on purpose: the same Google Shopping query
        # answered by either vendor is the same data, and switching vendor should not
        # throw away a warm cache.
        cache_key = cache.make_key("search", engine, clean_params)
        if cache_ttl > 0:
            cached = await cache.get_json(cache_key)
            if cached is not None:
                stat["cache_hits"] += 1
                cached["_buywise_cached"] = True
                return cached

        if breaker_open():
            stat["short_circuited"] += 1
            raise SearchApiQuotaExceeded(BREAKER["reason"] or "search API unavailable")

        query = {"engine": engine, "api_key": self.api_key, **self._extra, **clean_params}
        started = time.perf_counter()
        stat["calls"] += 1
        try:
            response = await request_with_retry(
                "GET",
                self.base_url,
                params=query,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        except httpx.HTTPError as exc:
            stat["failures"] += 1
            stat["last_error"] = type(exc).__name__
            logger.warning("%s %s transport error: %s", self.provider, engine, type(exc).__name__)
            raise SearchApiError(f"{engine} request failed: {type(exc).__name__}") from exc
        latency = int((time.perf_counter() - started) * 1000)
        stat["total_latency_ms"] += latency

        body_text = ""
        try:
            body_text = response.text[:400].lower()
        except Exception:  # pragma: no cover
            body_text = ""

        if response.status_code in (401, 403):
            stat["failures"] += 1
            stat["last_error"] = "unauthorized"
            _open_breaker(f"{self.provider} rejected the API key", self.cooldown)
            raise SearchApiAuthError(f"{self.provider} rejected the API key")
        if response.status_code == 429:
            stat["rate_limited"] += 1
            stat["last_error"] = "rate_limited"
            if any(m in body_text for m in _QUOTA_MARKERS):
                _open_breaker(f"{self.provider} search quota reached", self.cooldown)
                raise SearchApiQuotaExceeded(f"{self.provider} search quota reached")
            _open_breaker(f"{self.provider} rate limit", 60)
            raise SearchApiRateLimited(f"{self.provider} rate limit reached")
        if response.status_code >= 400:
            stat["failures"] += 1
            stat["last_error"] = f"http_{response.status_code}"
            if any(m in body_text for m in _QUOTA_MARKERS):
                _open_breaker(f"{self.provider} search quota reached", self.cooldown)
                raise SearchApiQuotaExceeded(f"{self.provider} search quota reached")
            raise SearchApiError(f"{engine} returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            stat["failures"] += 1
            raise SearchApiError(f"{self.provider} returned invalid JSON") from exc
        if isinstance(data, dict) and data.get("error"):
            message = str(data["error"])
            lowered = message.lower()
            # "Google hasn't returned any results for this query." is an empty result,
            # not a failure.
            if "hasn't returned any results" in lowered or "no results" in lowered:
                data = {"search_metadata": data.get("search_metadata", {}), "empty": True}
            else:
                stat["failures"] += 1
                stat["last_error"] = message[:120]
                if any(m in lowered for m in _QUOTA_MARKERS):
                    _open_breaker(f"{self.provider} search quota reached", self.cooldown)
                    raise SearchApiQuotaExceeded(f"{self.provider}: {message[:160]}")
                if "api key" in lowered or "api_key" in lowered or "unauthorized" in lowered:
                    _open_breaker(f"{self.provider} rejected the API key", self.cooldown)
                    raise SearchApiAuthError(f"{self.provider}: {message[:160]}")
                raise SearchApiError(f"{self.provider} {engine}: {message[:200]}")
        logger.info("%s %s ok in %dms", self.provider, engine, latency)
        if cache_ttl > 0:
            await cache.set_json(cache_key, data, cache_ttl)
        data["_buywise_cached"] = False
        return data


_client: SearchClient | None = None


def get_search_client() -> SearchClient:
    """The client for the active vendor. Rebuilt if configuration changes."""
    global _client
    settings = get_settings()
    provider = settings.active_search_provider
    key = settings.SEARCHAPI_API_KEY if provider == "searchapi" else settings.SERPAPI_API_KEY
    if _client is None or _client.provider != provider or _client.api_key != key:
        _client = SearchClient(provider, key)
    return _client


def search_stats() -> dict[str, Any]:
    out = {}
    for engine, s in STATS.items():
        calls = s["calls"] or 1
        out[engine] = {**s, "avg_latency_ms": int(s["total_latency_ms"] / calls)}
    return out
