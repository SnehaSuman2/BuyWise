"""HTTP client for Serper.dev.

A second search-data vendor, so a demo is not one exhausted quota away from
having nothing to show. It keeps its own circuit breaker: SerpApi running out
of searches must not stop BuyWise asking Serper, which was the whole point of
adding it.

Failures are raised as the same exception types the SerpApi client raises, so
everything downstream handles a dead vendor identically whichever one it was.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.core.cache import cache
from app.core.config import get_settings
from app.core.http import request_with_retry
from app.providers.search_client import (
    _QUOTA_MARKERS,
    SearchApiAuthError,
    SearchApiError,
    SearchApiQuotaExceeded,
    SearchApiRateLimited,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://google.serper.dev"
STATS: dict[str, dict[str, Any]] = {}
# Independent of the SerpApi breaker on purpose.
BREAKER: dict[str, Any] = {"open_until": 0.0, "reason": None}


def _stat(endpoint: str) -> dict[str, Any]:
    return STATS.setdefault(
        endpoint,
        {
            "calls": 0,
            "cache_hits": 0,
            "failures": 0,
            "short_circuited": 0,
            "stale_hits": 0,
            "total_latency_ms": 0,
            "last_error": None,
        },
    )


def breaker_open() -> bool:
    return BREAKER["open_until"] > time.time()


def reset_breaker() -> None:
    BREAKER.update({"open_until": 0.0, "reason": None})


def _open_breaker(reason: str, seconds: float) -> None:
    BREAKER["open_until"] = time.time() + seconds
    BREAKER["reason"] = reason
    logger.warning("Serper circuit opened for %ds: %s", int(seconds), reason)


def _cache_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """The payload as a cache key: the shopper's words normalised.

    Same reasoning as the SerpApi client. "iPhone 17" and "iphone  17!" are one
    question and should cost one credit, not three.
    """
    out = dict(payload)
    q = out.get("q")
    if isinstance(q, str):
        out["q"] = re.sub(r"[^a-z0-9+]+", " ", q.lower()).strip()
    return out


class SerperClient:
    name = "serper"

    def __init__(self, api_key: str) -> None:
        settings = get_settings()
        self.api_key = api_key
        self.timeout = settings.SERPAPI_TIMEOUT_SECONDS
        self.max_retries = settings.SERPAPI_MAX_RETRIES
        self.cooldown = settings.SEARCH_API_COOLDOWN_SECONDS

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _stale(self, key: str, stat: dict[str, Any]) -> dict[str, Any] | None:
        stale = await cache.get_json(key, allow_stale=True)
        if stale is None:
            return None
        stat["stale_hits"] += 1
        stale["_buywise_cached"] = True
        stale["_buywise_stale"] = True
        return stale

    async def post(
        self, endpoint: str, payload: dict[str, Any], *, cache_ttl: int = 3600
    ) -> dict[str, Any]:
        """One call to a Serper endpoint ("shopping", "search", "lens")."""
        if not self.enabled:
            raise SearchApiAuthError("No Serper API key is configured")
        stat = _stat(endpoint)
        body = {k: v for k, v in payload.items() if v is not None and v != ""}
        # Namespaced away from the SerpApi cache: same question, different answer
        # shape, so the two must never read each other's entries.
        cache_key = cache.make_key("serper", endpoint, _cache_payload(body))
        if cache_ttl > 0:
            cached = await cache.get_json(cache_key)
            if cached is not None:
                stat["cache_hits"] += 1
                cached["_buywise_cached"] = True
                return cached

        if breaker_open():
            stale = await self._stale(cache_key, stat) if cache_ttl > 0 else None
            if stale is not None:
                return stale
            stat["short_circuited"] += 1
            raise SearchApiQuotaExceeded(BREAKER["reason"] or "Serper unavailable")

        started = time.perf_counter()
        stat["calls"] += 1
        try:
            response = await request_with_retry(
                "POST",
                f"{BASE_URL}/{endpoint}",
                json=body,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        except httpx.HTTPError as exc:
            stat["failures"] += 1
            stat["last_error"] = type(exc).__name__
            raise SearchApiError(f"serper {endpoint} failed: {type(exc).__name__}") from exc
        stat["total_latency_ms"] += int((time.perf_counter() - started) * 1000)

        try:
            text = response.text[:400].lower()
        except Exception:  # pragma: no cover - defensive
            text = ""
        quota_hinted = any(m in text for m in _QUOTA_MARKERS)

        if response.status_code in (401, 403):
            stat["failures"] += 1
            # Serper reports an empty balance as 403 too, so the body decides
            # whether this is a bad key or simply no credits left.
            if quota_hinted:
                stat["last_error"] = "quota"
                _open_breaker("Serper credits exhausted", self.cooldown)
                stale = await self._stale(cache_key, stat) if cache_ttl > 0 else None
                if stale is not None:
                    return stale
                raise SearchApiQuotaExceeded("Serper credits exhausted")
            stat["last_error"] = "unauthorized"
            _open_breaker("Serper rejected the API key", self.cooldown)
            raise SearchApiAuthError("Serper rejected the API key")
        if response.status_code == 429:
            stat["failures"] += 1
            stat["last_error"] = "rate_limited"
            _open_breaker("Serper rate limit", 60)
            raise SearchApiRateLimited("Serper rate limit reached")
        if response.status_code >= 400:
            stat["failures"] += 1
            stat["last_error"] = f"http_{response.status_code}"
            if quota_hinted:
                _open_breaker("Serper credits exhausted", self.cooldown)
                raise SearchApiQuotaExceeded("Serper credits exhausted")
            raise SearchApiError(f"serper {endpoint} returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            stat["failures"] += 1
            raise SearchApiError("Serper returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise SearchApiError("Serper returned an unexpected payload")
        if cache_ttl > 0:
            await cache.set_json(cache_key, data, cache_ttl)
        data["_buywise_cached"] = False
        return data


_client: SerperClient | None = None


def get_serper_client() -> SerperClient:
    global _client
    key = get_settings().SERPER_API_KEY
    if _client is None or _client.api_key != key:
        _client = SerperClient(key)
    return _client


def serper_stats() -> dict[str, Any]:
    out = {}
    for endpoint, s in STATS.items():
        calls = s["calls"] or 1
        out[endpoint] = {**s, "avg_latency_ms": int(s["total_latency_ms"] / calls)}
    return out
