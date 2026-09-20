"""Shared database cache and the scheduled-job endpoint."""

import pytest

from app.core.cache import STATS, cache
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_database_cache_round_trip_survives_process_memory():
    key = cache.make_key("search", "google_shopping", {"q": "iphone 17"})
    await cache.set_json(key, {"shopping_results": [{"title": "x"}]}, ttl=600)
    # Drop the in-process copy: another worker, or this one after a restart.
    cache._memory._store.clear()
    got = await cache.get_json(key)
    assert got == {"shopping_results": [{"title": "x"}]}
    assert STATS["backend"] == "database"


@pytest.mark.asyncio
async def test_expired_rows_are_ignored_and_purged():
    key = cache.make_key("search", "amazon", {"k": "old"})
    await cache._database.set(key, '{"stale": true}', ttl=-1)
    cache._memory._store.clear()
    assert await cache.get_json(key) is None
    await cache._database.set(key, '{"stale": true}', ttl=-1)
    assert await cache.purge_expired() >= 1


@pytest.mark.asyncio
async def test_internal_jobs_require_the_cron_secret(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "CRON_SECRET", "")
    assert (await client.post("/api/v1/internal/jobs/cleanup")).status_code == 401

    monkeypatch.setattr(s, "CRON_SECRET", "s3cret-value")
    wrong = await client.post("/api/v1/internal/jobs/cleanup", headers={"X-Cron-Secret": "nope"})
    assert wrong.status_code == 401
    unknown = await client.post(
        "/api/v1/internal/jobs/nothing", headers={"X-Cron-Secret": "s3cret-value"}
    )
    assert unknown.status_code == 404
    ok = await client.post(
        "/api/v1/internal/jobs/cleanup", headers={"X-Cron-Secret": "s3cret-value"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["job"] == "cleanup" and ok.json()["status"] == "success"
    assert "expired_cache_rows_deleted" in ok.json()
