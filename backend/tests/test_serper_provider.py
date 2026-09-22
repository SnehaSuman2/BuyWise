"""The second search vendor: its normaliser, its own circuit breaker, and the
chain that reaches it only when the first vendor has nothing."""

import pytest

from app.core.config import get_settings
from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.providers.chain import ChainedProductSearchProvider
from app.providers.serper.google_shopping import (
    SerperShoppingProvider,
    normalize_serper_shopping,
)


def test_serper_shopping_fields_are_mapped():
    listing = normalize_serper_shopping(
        {
            "title": "Apple iPhone 17 256GB Black",
            "source": "Croma",
            "link": "https://www.croma.com/p/12345",
            "price": "₹82,900",
            "delivery": "Free delivery",
            "imageUrl": "https://img.example/1.jpg",
            "rating": 4.5,
            "ratingCount": 1234,
            "offers": "4",
            "productId": "987654321",
        }
    )
    assert listing is not None
    assert listing.title == "Apple iPhone 17 256GB Black"
    assert listing.price == 82900
    assert listing.retailer_name == "Croma"
    assert listing.retailer_domain == "croma.com"
    assert listing.rating == 4.5 and listing.rating_count == 1234
    assert listing.identifiers["google_product_id"] == "987654321"
    assert listing.shipping_known is True and listing.shipping_price == 0
    # Several merchants for one product is what marks it worth a store lookup.
    assert listing.multiple_sources is True
    assert listing.source_provider == "serper"


def test_serper_normaliser_tolerates_missing_and_renamed_fields():
    assert normalize_serper_shopping({"title": "", "price": "1"}) is None
    assert normalize_serper_shopping({}) is None
    lean = normalize_serper_shopping({"title": "Some Product", "seller": "Shop", "priceRaw": "999"})
    assert lean is not None and lean.price == 999 and lean.retailer_name == "Shop"
    assert lean.multiple_sources is False  # no offer count means no claim


def test_a_single_merchant_is_not_claimed_to_be_several():
    one = normalize_serper_shopping({"title": "X", "source": "Y", "price": "10", "offers": "1"})
    assert one is not None and one.multiple_sources is False


class _Fake:
    def __init__(self, name, items=None, ok=True, enabled=True, boom=False):
        self.name, self.engine, self.enabled, self.is_demo = name, "google_shopping", enabled, False
        self._items, self._ok, self._boom = items or [], ok, boom
        self.calls = 0

    async def search_products(self, query, *, max_results=20, min_price=None, max_price=None):
        self.calls += 1
        if self._boom:
            raise RuntimeError("vendor exploded")
        if not self._ok:
            return ProviderResult.failure(self.name, self.engine, "quota exhausted")
        return ProviderResult(items=list(self._items), provider=self.name, engine=self.engine)


def _listing(title="A thing"):
    return NormalizedListing(title=title, price=100.0, retailer_name="Shop")


@pytest.mark.asyncio
async def test_chain_stops_at_the_first_vendor_that_answers():
    first, second = _Fake("serpapi", [_listing()]), _Fake("serper", [_listing()])
    chain = ChainedProductSearchProvider([first, second])
    res = await chain.search_products("iphone 17")
    assert res.ok and len(res.items) == 1
    assert first.calls == 1 and second.calls == 0, "the second quota must not be spent"
    assert chain.name == "serpapi"


@pytest.mark.asyncio
async def test_chain_falls_through_when_the_first_vendor_is_out_of_quota():
    first, second = _Fake("serpapi", ok=False), _Fake("serper", [_listing("From Serper")])
    chain = ChainedProductSearchProvider([first, second])
    res = await chain.search_products("iphone 17")
    assert res.ok and res.items[0].title == "From Serper"
    assert first.calls == 1 and second.calls == 1
    assert chain.name == "serper", "the answering vendor is the one reported"


@pytest.mark.asyncio
async def test_chain_survives_a_vendor_that_raises():
    first, second = _Fake("serpapi", boom=True), _Fake("serper", [_listing()])
    chain = ChainedProductSearchProvider([first, second])
    res = await chain.search_products("anything")
    assert res.ok and res.items


@pytest.mark.asyncio
async def test_chain_falls_through_on_an_empty_but_successful_answer():
    first, second = _Fake("serpapi", []), _Fake("serper", [_listing()])
    chain = ChainedProductSearchProvider([first, second])
    res = await chain.search_products("obscure thing")
    assert res.ok and res.items and second.calls == 1


@pytest.mark.asyncio
async def test_chain_reports_failure_when_every_vendor_is_down():
    chain = ChainedProductSearchProvider([_Fake("serpapi", ok=False), _Fake("serper", ok=False)])
    res = await chain.search_products("x")
    assert not res.ok


@pytest.mark.asyncio
async def test_disabled_vendors_are_skipped():
    off, on = _Fake("serpapi", [_listing()], enabled=False), _Fake("serper", [_listing()])
    chain = ChainedProductSearchProvider([off, on])
    res = await chain.search_products("x")
    assert res.ok and off.calls == 0 and on.calls == 1


def test_serper_breaker_is_independent_of_serpapi(monkeypatch):
    """SerpApi running dry must never stop us asking Serper."""
    from app.providers import search_client
    from app.providers.serper import client as serper_client

    serper_client.reset_breaker()
    search_client.reset_breaker()
    search_client._open_breaker("serpapi quota reached", 600)
    assert search_client.breaker_open() is True
    assert serper_client.breaker_open() is False
    search_client.reset_breaker()


def test_serper_is_only_enabled_with_a_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SERPER_API_KEY", "")
    assert SerperShoppingProvider().enabled is False
    monkeypatch.setattr(settings, "SERPER_API_KEY", "abc123")
    assert SerperShoppingProvider().enabled is True
    assert settings.serper_enabled is True
    assert settings.any_search_vendor_enabled is True


def test_registry_chains_both_vendors_when_both_are_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "serp-key")
    monkeypatch.setattr(settings, "SEARCHAPI_API_KEY", "")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    providers = registry.product_search_providers()
    assert len(providers) == 1, "one chained provider, not two called in parallel"
    names = [p.name for p in providers[0].providers]
    assert names[0] == "serpapi" and "serper" in names
    assert registry.provider_status()["serper_configured"] is True


def test_serper_alone_still_answers_searches(monkeypatch):
    """The whole point: no SerpApi key at all, and search still has a vendor."""
    settings = get_settings()
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "")
    monkeypatch.setattr(settings, "SEARCHAPI_API_KEY", "")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    providers = registry.product_search_providers()
    assert [p.name for p in providers[0].providers] == ["serper"]
    assert providers[0].enabled is True


def test_serper_lens_results_are_normalised():
    from app.providers.serper.google_lens import normalize_serper_lens

    listing = normalize_serper_lens(
        {
            "title": "Sony WH-1000XM5 Headphones",
            "link": "https://www.amazon.in/dp/B09XS7JWHH",
            "source": "Amazon.in",
            "price": "₹26,990",
            "imageUrl": "https://img/1.jpg",
        }
    )
    assert listing is not None
    assert listing.price == 26990 and listing.retailer_domain == "amazon.in"
    assert listing.source_provider == "serper" and listing.source_engine == "google_lens"
    assert normalize_serper_lens({"link": "x"}) is None
    nested = normalize_serper_lens({"title": "T", "price": {"value": "₹1,200"}})
    assert nested is not None and nested.price == 1200


def test_photo_search_keeps_a_fallback_vendor(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "serp-key")
    monkeypatch.setattr(settings, "SEARCHAPI_API_KEY", "")
    monkeypatch.setattr(settings, "SERPER_API_KEY", "serper-key")
    names = [f"{p.name}:{p.engine}" for p in registry.image_search_providers()]
    assert any(n.startswith("serper") for n in names), names
    assert registry.provider_status()["engines"]["serper_lens"] is True
