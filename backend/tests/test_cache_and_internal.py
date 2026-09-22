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
async def test_expired_rows_are_ignored_but_kept_for_the_stale_fallback():
    from datetime import timedelta

    key = cache.make_key("search", "amazon", {"k": "old"})
    await cache._database.set(key, '{"stale": true}', ttl=-1)
    cache._memory._store.clear()
    # Expired, so not served as a fresh answer...
    assert await cache.get_json(key) is None
    # ...but still there for the quota fallback, and not purged while recent.
    cache._memory._store.clear()
    assert await cache.get_json(key, allow_stale=True) == {"stale": True}
    assert await cache.purge_expired() == 0
    # Once it is older than the grace period it goes.
    assert await cache._database.purge_expired(grace=timedelta(seconds=0)) >= 1
    cache._memory._store.clear()
    assert await cache.get_json(key, allow_stale=True) is None


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


@pytest.mark.asyncio
async def test_cleanup_removes_old_uploads_but_keeps_dotfiles(client, monkeypatch, tmp_path):
    import os
    import time
    from pathlib import Path

    from app.workers import jobs

    upload_dir = Path(jobs.__file__).resolve().parent.parent.parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    keep = upload_dir / ".gitkeep"
    keep.touch()
    old = upload_dir / "old-test-upload.jpg"
    old.write_bytes(b"\xff\xd8test")
    two_days_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(old, (two_days_ago, two_days_ago))
    os.utime(keep, (two_days_ago, two_days_ago))
    fresh = upload_dir / "fresh-test-upload.jpg"
    fresh.write_bytes(b"\xff\xd8test")
    try:
        monkeypatch.setattr(get_settings(), "CRON_SECRET", "s3cret-value")
        r = await client.post(
            "/api/v1/internal/jobs/cleanup", headers={"X-Cron-Secret": "s3cret-value"}
        )
        assert r.status_code == 200 and r.json()["uploads_deleted"] >= 1
        assert keep.exists() and fresh.exists() and not old.exists()
    finally:
        fresh.unlink(missing_ok=True)
        old.unlink(missing_ok=True)
