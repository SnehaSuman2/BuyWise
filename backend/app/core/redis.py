"""Redis connection management (optional)."""

from typing import Optional

from app.core.cache import cache
from app.core.config import get_settings

settings = get_settings()


async def get_redis() -> Optional[object]:
    """Return the Redis client if configured and reachable, else None."""
    backend = await cache._backend()
    return None if backend is cache._memory else backend


async def close_redis() -> None:
    await cache.close()
