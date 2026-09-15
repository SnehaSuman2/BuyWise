"""Shared SerpApi HTTP client.

- One key for every engine (SERPAPI_API_KEY).
- Timeouts, bounded retries with backoff, rate-limit handling.
- Response caching to keep API costs down.
- Per-engine call statistics for the diagnostics endpoint.
- The API key is never logged (see core.logging redaction).
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

SERPAPI_URL = "https://serpapi.com/search.json"

STATS: dict[str, dict[str, Any]] = {}


def _stat(engine: str) -> dict[str, Any]:
    return STATS.setdefault(
        engine,
        {
            "calls": 0,
            "cache_hits": 0,
            "failures": 0,
            "rate_limited": 0,
            "total_latency_ms": 0,
            "last_error": None,
        },
    )


class SerpApiError(Exception):
    """Base error for SerpApi failures."""


class SerpApiAuthError(SerpApiError):
    pass


class SerpApiRateLimited(SerpApiError):
    pass


class SerpApiClient:
    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.SERPAPI_API_KEY
        self.timeout = settings.SERPAPI_TIMEOUT_SECONDS
        self.max_retries = settings.SERPAPI_MAX_RETRIES

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search(
        self, engine: str, params: dict[str, Any], *, cache_ttl: int = 3600
    ) -> dict[str, Any]:
        if not self.enabled:
            raise SerpApiAuthError("SERPAPI_API_KEY is not configured")
        stat = _stat(engine)
        clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
        cache_key = cache.make_key("serpapi", engine, clean_params)
        if cache_ttl > 0:
            cached = await cache.get_json(cache_key)
            if cached is not None:
                stat["cache_hits"] += 1
                cached["_buywise_cached"] = True
                return cached

        query = {"engine": engine, "api_key": self.api_key, "output": "json", **clean_params}
        started = time.perf_counter()
        stat["calls"] += 1
        try:
            response = await request_with_retry(
                "GET", SERPAPI_URL, params=query, timeout=self.timeout, max_retries=self.max_retries
            )
        except httpx.HTTPError as exc:
            stat["failures"] += 1
            stat["last_error"] = type(exc).__name__
            logger.warning("SerpApi %s transport error: %s", engine, type(exc).__name__)
            raise SerpApiError(f"SerpApi {engine} request failed: {type(exc).__name__}") from exc
        latency = int((time.perf_counter() - started) * 1000)
        stat["total_latency_ms"] += latency

        if response.status_code == 401:
            stat["failures"] += 1
            stat["last_error"] = "unauthorized"
            raise SerpApiAuthError("SerpApi rejected the API key")
        if response.status_code == 429:
            stat["rate_limited"] += 1
            stat["last_error"] = "rate_limited"
            raise SerpApiRateLimited("SerpApi rate limit reached")
        if response.status_code >= 400:
            stat["failures"] += 1
            stat["last_error"] = f"http_{response.status_code}"
            raise SerpApiError(f"SerpApi {engine} returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            stat["failures"] += 1
            raise SerpApiError("SerpApi returned invalid JSON") from exc
        if isinstance(data, dict) and data.get("error"):
            # "Google hasn't returned any results for this query." is a normal empty result, not a failure.
            message = str(data["error"])
            if "hasn't returned any results" in message or "No results" in message:
                data = {"search_metadata": data.get("search_metadata", {}), "empty": True}
            else:
                stat["failures"] += 1
                stat["last_error"] = message[:120]
                raise SerpApiError(f"SerpApi {engine}: {message[:200]}")
        logger.info("SerpApi %s ok in %dms", engine, latency)
        if cache_ttl > 0:
            await cache.set_json(cache_key, data, cache_ttl)
        data["_buywise_cached"] = False
        return data


_client: SerpApiClient | None = None


def get_serpapi_client() -> SerpApiClient:
    global _client
    if _client is None:
        _client = SerpApiClient()
    return _client


def serpapi_stats() -> dict[str, Any]:
    out = {}
    for engine, s in STATS.items():
        calls = s["calls"] or 1
        out[engine] = {**s, "avg_latency_ms": int(s["total_latency_ms"] / calls)}
    return out
