"""Making a small search allowance go further: shared cache keys and stale answers."""

import pytest

from app.core.cache import cache
from app.providers import search_client as sc


@pytest.fixture(autouse=True)
def _clean_breaker():
    sc.reset_breaker()
    cache._memory._store.clear()
    yield
    sc.reset_breaker()


class FakeResponse:
    def __init__(self, status_code, payload, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)
        self.headers = {}

    def json(self):
        return self._payload


def test_spelling_of_a_query_does_not_change_its_cache_key():
    def key(q):
        return cache.make_key("search", "google_shopping", sc._cache_params({"q": q, "gl": "in"}))  # noqa: E731

    assert key("iPhone 17") == key("iphone 17") == key("iphone  17") == key("iPhone 17!")
    # Genuinely different queries stay different.
    assert key("iphone 17") != key("iphone 17 pro")
    assert key("iphone 17") != key("apple iphone 17")
    # Non-query parameters still separate entries.
    a = cache.make_key("search", "google_shopping", sc._cache_params({"q": "x", "gl": "in"}))
    b = cache.make_key("search", "google_shopping", sc._cache_params({"q": "x", "gl": "us"}))
    assert a != b


@pytest.mark.asyncio
async def test_a_repeat_search_costs_no_call(monkeypatch):
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append(kwargs["params"]["q"])
        return FakeResponse(
            200, {"shopping_results": [{"title": "Apple iPhone 17", "extracted_price": 79900}]}
        )

    monkeypatch.setattr(sc, "request_with_retry", fake_request)
    client = sc.SearchClient("serpapi", "k")
    first = await client.search("google_shopping", {"q": "iPhone 17"}, cache_ttl=600)
    assert first["_buywise_cached"] is False
    second = await client.search("google_shopping", {"q": "iphone  17"}, cache_ttl=600)
    assert second["_buywise_cached"] is True
    assert len(calls) == 1, calls


@pytest.mark.asyncio
async def test_expired_results_are_served_when_the_quota_is_gone(monkeypatch):
    from app.core.config import get_settings

    # One tier only, so "expired" means expired everywhere and the test is about
    # the stale path rather than about which tier answered.
    monkeypatch.setattr(get_settings(), "CACHE_BACKEND", "memory")
    payload = {"shopping_results": [{"title": "Apple iPhone 17", "extracted_price": 79900}]}
    responses = [FakeResponse(200, payload)]

    async def fake_request(method, url, **kwargs):
        if responses:
            return responses.pop(0)
        return FakeResponse(429, {"error": {"message": "You exceeded your current quota"}}, "quota")

    monkeypatch.setattr(sc, "request_with_retry", fake_request)
    client = sc.SearchClient("serpapi", "k")

    # A search with a one-second window, then let it expire.
    await client.search("google_shopping", {"q": "iphone 17"}, cache_ttl=1)
    key = cache.make_key("search", "google_shopping", sc._cache_params({"q": "iphone 17"}))
    entry = cache._memory._store[key]
    cache._memory._store[key] = (0.0, entry[1])  # expired

    out = await client.search("google_shopping", {"q": "iphone 17"}, cache_ttl=600)
    assert out["_buywise_stale"] is True and out["shopping_results"], out
    assert sc.breaker_open()

    # With the breaker open, a query never seen before still fails honestly.
    with pytest.raises(sc.SearchApiQuotaExceeded):
        await client.search("google_shopping", {"q": "something never searched"}, cache_ttl=600)


@pytest.mark.asyncio
async def test_search_tells_the_shopper_results_are_old(client, monkeypatch):
    from app.providers import registry
    from app.providers.base import NormalizedListing, ProviderResult

    class StaleProvider:
        name, engine, enabled = "test", "fake_shopping", True

        async def search_products(self, query, *, max_results=20, min_price=None, max_price=None):
            return ProviderResult(
                items=[
                    NormalizedListing(
                        title="Apple iPhone 17 256GB",
                        url="https://www.croma.com/p/1",
                        price=79900,
                        retailer_name="Croma",
                        retailer_domain="croma.com",
                        source_provider="test",
                    )
                ],
                provider=self.name,
                engine=self.engine,
                cached=True,
                stale=True,
            )

    class NoAmazon:
        name, engine, enabled, retailer_slug = "test", "fake_amazon", True, "amazon-india"

        async def search_retailer(self, query, *, max_results=10):
            return ProviderResult(items=[], provider=self.name, engine=self.engine)

    monkeypatch.setattr(registry, "product_search_providers", lambda: [StaleProvider()])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [NoAmazon()])
    r = await client.post("/api/v1/search", json={"query": "iphone 17"})
    assert r.status_code == 200
    assert r.json()["results"]
    assert any("most recent results" in w for w in r.json()["meta"]["warnings"]), r.json()["meta"]
