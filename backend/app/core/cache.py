"""Cache abstraction: Redis when configured, otherwise the application database
fronted by a small in-process cache.

Used to avoid repeated calls to expensive external APIs (search data, AI).
Never cache user-specific or sensitive data here.

Why a database tier: the original in-memory cache was per process and vanished on
every restart. On a host that runs two workers and sleeps when idle, that meant a
shopper repeating a search minutes later paid for a fresh search-API call almost
every time. Rows in `api_cache` are shared by every worker and survive restarts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

STATS = {"hits": 0, "misses": 0, "sets": 0, "backend": "memory"}

# How long an expired cache row is kept so it can still answer when the search
# provider is unreachable or out of quota.
STALE_GRACE = timedelta(days=7)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str, allow_stale: bool = False) -> str | None:
        item = self._store.get(key)
        if not item:
            return None
        expires, value = item
        if expires < time.time():
            # Expired entries are kept, not dropped: they are the material the
            # stale fallback uses when the provider is out of quota. Size-based
            # eviction below still bounds the store.
            return value if allow_stale else None
        return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        async with self._lock:
            if len(self._store) > 5000:
                now = time.time()
                for k in [k for k, (exp, _) in self._store.items() if exp < now][:1000]:
                    self._store.pop(k, None)
                if len(self._store) > 5000:
                    for k in list(self._store.keys())[:500]:
                        self._store.pop(k, None)
            self._store[key] = (time.time() + ttl, value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class _DatabaseCache:
    """Restart-proof cache rows in the application database.

    Each call opens its own short session so cache traffic never entangles with a
    request's transaction. Expired rows are ignored on read and swept by the
    cleanup job (and opportunistically here, every few hundred writes).
    """

    def __init__(self) -> None:
        self._writes = 0

    @staticmethod
    def _factory():
        from app.core.database import async_session_factory

        return async_session_factory

    async def get(self, key: str, allow_stale: bool = False) -> str | None:
        from app.models.cache import ApiCache

        async with self._factory()() as session:
            row = await session.get(ApiCache, key)
            if row is None:
                return None
            expires = row.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < _utcnow():
                # Kept, not deleted: an expired answer is still the best answer
                # available while the provider is unreachable or out of quota.
                # purge_expired drops rows once they are too old to be useful.
                return row.value if allow_stale else None
            return row.value

    async def set(self, key: str, value: str, ttl: int) -> None:
        from app.models.cache import ApiCache

        async with self._factory()() as session:
            await session.merge(
                ApiCache(key=key, value=value, expires_at=_utcnow() + timedelta(seconds=ttl))
            )
            await session.commit()
        self._writes += 1
        if self._writes % 200 == 0:
            await self.purge_expired()

    async def delete(self, key: str) -> None:
        from app.models.cache import ApiCache

        async with self._factory()() as session:
            row = await session.get(ApiCache, key)
            if row is not None:
                await session.delete(row)
                await session.commit()

    async def purge_expired(self, grace: timedelta = STALE_GRACE) -> int:
        """Drop rows expired longer ago than the grace period.

        Recently-expired rows are deliberately kept: they are what the search
        layer falls back on when the provider is out of quota, so deleting them
        the moment they expire would throw away the safety net.
        """
        from sqlalchemy import delete

        from app.models.cache import ApiCache

        async with self._factory()() as session:
            result = await session.execute(
                delete(ApiCache).where(ApiCache.expires_at < _utcnow() - grace)
            )
            await session.commit()
            return int(result.rowcount or 0)


class Cache:
    def __init__(self) -> None:
        self._memory = _MemoryCache()
        self._database = _DatabaseCache()
        self._redis = None
        self._redis_failed = False
        self._database_failed_at: float | None = None

    async def _backend(self):
        settings = get_settings()
        if settings.redis_enabled and not self._redis_failed:
            if self._redis is None:
                try:
                    import redis.asyncio as aioredis

                    self._redis = aioredis.from_url(
                        settings.REDIS_URL,
                        encoding="utf-8",
                        decode_responses=True,
                        socket_timeout=2,
                    )
                    await self._redis.ping()
                    STATS["backend"] = "redis"
                except Exception as exc:  # pragma: no cover - depends on environment
                    logger.warning(
                        "Redis unavailable (%s); falling back to database cache",
                        type(exc).__name__,
                    )
                    self._redis_failed = True
                    self._redis = None
            if self._redis is not None:
                return self._redis
        if settings.CACHE_BACKEND == "memory":
            STATS["backend"] = "memory"
            return self._memory
        # A database outage must not take search down with it: after a failure the
        # memory tier serves alone for a minute, then the database is tried again.
        if self._database_failed_at and time.time() - self._database_failed_at < 60:
            return self._memory
        STATS["backend"] = "database"
        return self._database

    @staticmethod
    def make_key(namespace: str, *parts: Any) -> str:
        raw = json.dumps(parts, sort_keys=True, default=str)
        return f"buywise:{namespace}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"

    async def get_json(self, key: str, allow_stale: bool = False) -> Any | None:
        """Read a cached value. With allow_stale, an expired value is returned too.

        Stale is for when the alternative is nothing: the search vendor is out of
        quota or unreachable, and yesterday's prices, clearly labelled, beat an
        empty page.
        """
        # The memory tier fronts every backend so a hot key costs no round trip.
        value = await self._memory.get(key, allow_stale)
        if value is None:
            backend = await self._backend()
            if backend is not self._memory:
                try:
                    value = (
                        await backend.get(key, allow_stale)
                        if backend is self._database
                        else await backend.get(key)
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("Cache get failed: %s", type(exc).__name__)
                    if backend is self._database:
                        self._database_failed_at = time.time()
                    value = None
        if value is None:
            STATS["misses"] += 1
            return None
        STATS["hits"] += 1
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        payload = json.dumps(value, default=str)
        # Keep the in-process copy short-lived so a value evicted or refreshed
        # elsewhere is picked up within minutes by every worker.
        await self._memory.set(key, payload, min(ttl, 300))
        backend = await self._backend()
        if backend is self._memory:
            await self._memory.set(key, payload, ttl)
            STATS["sets"] += 1
            return
        try:
            if backend is self._database:
                await backend.set(key, payload, ttl)
            else:
                await backend.set(key, payload, ex=ttl)
            STATS["sets"] += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache set failed: %s", type(exc).__name__)
            if backend is self._database:
                self._database_failed_at = time.time()

    async def delete(self, key: str) -> None:
        await self._memory.delete(key)
        backend = await self._backend()
        if backend is self._memory:
            return
        try:
            await backend.delete(key)
        except Exception:  # pragma: no cover
            pass

    async def purge_expired(self) -> int:
        """Remove cache rows too old to serve even as a stale answer."""
        try:
            return await self._database.purge_expired()
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache purge failed: %s", type(exc).__name__)
            return 0

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # pragma: no cover
                pass
            self._redis = None


cache = Cache()
