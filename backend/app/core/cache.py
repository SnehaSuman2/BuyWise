"""Cache abstraction: Redis when configured, in-process TTL cache otherwise.

Used to avoid repeated calls to expensive external APIs (SerpApi, OpenAI).
Never cache user-specific or sensitive data here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

STATS = {"hits": 0, "misses": 0, "sets": 0, "backend": "memory"}


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if not item:
            return None
        expires, value = item
        if expires < time.time():
            self._store.pop(key, None)
            return None
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


class Cache:
    def __init__(self) -> None:
        self._memory = _MemoryCache()
        self._redis = None
        self._redis_failed = False

    async def _backend(self):
        settings = get_settings()
        if not settings.redis_enabled or self._redis_failed:
            return self._memory
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    settings.REDIS_URL, encoding="utf-8", decode_responses=True, socket_timeout=2
                )
                await self._redis.ping()
                STATS["backend"] = "redis"
            except Exception as exc:  # pragma: no cover - depends on environment
                logger.warning(
                    "Redis unavailable (%s); falling back to in-memory cache", type(exc).__name__
                )
                self._redis_failed = True
                self._redis = None
                return self._memory
        return self._redis

    @staticmethod
    def make_key(namespace: str, *parts: Any) -> str:
        raw = json.dumps(parts, sort_keys=True, default=str)
        return f"buywise:{namespace}:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"

    async def get_json(self, key: str) -> Any | None:
        backend = await self._backend()
        try:
            value = await backend.get(key)
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache get failed: %s", type(exc).__name__)
            return None
        if value is None:
            STATS["misses"] += 1
            return None
        STATS["hits"] += 1
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        backend = await self._backend()
        try:
            payload = json.dumps(value, default=str)
            if backend is self._memory:
                await backend.set(key, payload, ttl)
            else:
                await backend.set(key, payload, ex=ttl)
            STATS["sets"] += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache set failed: %s", type(exc).__name__)

    async def delete(self, key: str) -> None:
        backend = await self._backend()
        try:
            await backend.delete(key)
        except Exception:  # pragma: no cover
            pass

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # pragma: no cover
                pass
            self._redis = None


cache = Cache()
