"""Search-data vendor layer: vendor selection, quota circuit breaker, SearchApi shapes."""

import pytest

from app.core.config import get_settings
from app.providers import search_client as sc
from app.providers.serpapi.amazon_product import adapt_searchapi_product, normalize_amazon_product
from app.providers.serpapi.amazon_search import AmazonSearchProvider, normalize_amazon_result
from app.providers.serpapi.google_lens import normalize_visual_match
from app.providers.serpapi.google_shopping import GoogleShoppingProvider, normalize_shopping_result


@pytest.fixture(autouse=True)
def _clean_breaker():
    sc.reset_breaker()
    yield
    sc.reset_breaker()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_vendor_selection_prefers_searchapi_when_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "SERPAPI_API_KEY", "serp-key")
    monkeypatch.setattr(s, "SEARCHAPI_API_KEY", "")
    monkeypatch.setattr(s, "SEARCH_PROVIDER", "auto")
    assert s.active_search_provider == "serpapi" and s.search_api_enabled
    assert sc.get_search_client().provider == "serpapi"

    monkeypatch.setattr(s, "SEARCHAPI_API_KEY", "sa-key")
    assert s.active_search_provider == "searchapi"
    assert sc.get_search_client().provider == "searchapi"
    assert sc.get_search_client().base_url.startswith("https://www.searchapi.io/")

    monkeypatch.setattr(s, "SEARCH_PROVIDER", "serpapi")
    assert sc.get_search_client().provider == "serpapi"

    monkeypatch.setattr(s, "SERPAPI_API_KEY", "")
    monkeypatch.setattr(s, "SEARCHAPI_API_KEY", "")
    assert not s.search_api_enabled and not s.serpapi_enabled


@pytest.mark.asyncio
async def test_quota_error_opens_breaker_and_short_circuits(monkeypatch):
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append(kwargs["params"]["engine"])
        return FakeResponse(
            200, {"error": "You have exhausted your monthly searches. Upgrade your plan."}
        )

    monkeypatch.setattr(sc, "request_with_retry", fake_request)
    client = sc.SearchClient("serpapi", "k")
    with pytest.raises(sc.SearchApiQuotaExceeded):
        await client.search("google_shopping", {"q": "iphone 17"}, cache_ttl=0)
    assert sc.breaker_open() and sc.breaker_status()["reason"]
    # The next call, any engine, fails instantly without touching the network.
    with pytest.raises(sc.SearchApiQuotaExceeded):
        await client.search("amazon", {"k": "iphone 17"}, cache_ttl=0)
    assert calls == ["google_shopping"]
    assert sc.STATS["amazon"]["short_circuited"] == 1


@pytest.mark.asyncio
async def test_rejected_key_opens_breaker(monkeypatch):
    async def fake_request(method, url, **kwargs):
        return FakeResponse(401, {"error": "Invalid API key"})

    monkeypatch.setattr(sc, "request_with_retry", fake_request)
    client = sc.SearchClient("searchapi", "bad")
    with pytest.raises(sc.SearchApiAuthError):
        await client.search("google", {"q": "x"}, cache_ttl=0)
    assert sc.breaker_open()


@pytest.mark.asyncio
async def test_empty_result_is_not_a_failure(monkeypatch):
    async def fake_request(method, url, **kwargs):
        return FakeResponse(200, {"error": "Google hasn't returned any results for this query."})

    monkeypatch.setattr(sc, "request_with_retry", fake_request)
    client = sc.SearchClient("serpapi", "k")
    data = await client.search("google_shopping", {"q": "zzzz"}, cache_ttl=0)
    assert data.get("empty") is True and not sc.breaker_open()


@pytest.mark.asyncio
async def test_engine_and_parameter_names_follow_the_vendor(monkeypatch):
    seen = []

    class FakeClient:
        def __init__(self, provider):
            self.provider = provider

        async def search(self, engine, params, *, cache_ttl=0):
            seen.append((self.provider, engine, dict(params)))
            return {"organic_results": [], "shopping_results": []}

    import app.providers.serpapi.amazon_search as amz
    import app.providers.serpapi.google_shopping as gs

    for provider in ("serpapi", "searchapi"):
        monkeypatch.setattr(amz, "get_search_client", lambda p=provider: FakeClient(p))
        monkeypatch.setattr(gs, "get_search_client", lambda p=provider: FakeClient(p))
        await AmazonSearchProvider().search_retailer("iphone 17")
        await GoogleShoppingProvider().search_products("iphone 17", min_price=1000)

    by_vendor = {(p, e): params for p, e, params in seen}
    assert "k" in by_vendor[("serpapi", "amazon")]
    assert by_vendor[("searchapi", "amazon_search")]["q"] == "iphone 17"
    assert "num" in by_vendor[("serpapi", "google_shopping")]
    assert "tbs" in by_vendor[("serpapi", "google_shopping")]
    assert "num" not in by_vendor[("searchapi", "google_shopping")]
    assert "tbs" not in by_vendor[("searchapi", "google_shopping")]


def test_searchapi_shopping_and_amazon_fields_normalize():
    shopping = normalize_shopping_result(
        {
            "title": "Apple iPhone 17 (256 GB) - Black",
            "price": "₹79,900",
            "extracted_price": 79900,
            "seller": "Croma",
            "product_link": "https://www.croma.com/apple-iphone-17/p/1",
            "product_id": "123",
            "thumbnail": "https://img/x.jpg",
            "rating": 4.6,
            "reviews": 120,
            "delivery": "Free delivery",
        },
        provider="searchapi",
    )
    assert shopping and shopping.retailer_name == "Croma" and shopping.price == 79900
    assert shopping.url and "croma.com" in shopping.url and shopping.shipping_price == 0.0
    assert shopping.source_provider == "searchapi"

    amazon = normalize_amazon_result(
        {
            "title": "Apple iPhone 17 (256 GB) - Black",
            "asin": "B0TEST1234",
            "price": "₹79,900",
            "extracted_price": 79900,
            "link": "https://www.amazon.in/dp/B0TEST1234",
            "is_prime": True,
            "rating": 4.5,
            "reviews": 2000,
        },
        "amazon.in",
        provider="searchapi",
    )
    assert amazon and amazon.shipping_price == 0.0 and amazon.shipping_known
    assert amazon.identifiers["asin"] == "B0TEST1234" and amazon.source_provider == "searchapi"


def test_searchapi_lens_price_string_normalizes():
    item = {
        "title": "Sony WH-1000XM5",
        "link": "https://www.flipkart.com/sony-wh-1000xm5/p/itm1",
        "source": "Flipkart",
        "price": "₹24,990",
        "extracted_price": 24990,
        "currency": "INR",
        "thumbnail": "https://img/y.jpg",
    }
    listing = normalize_visual_match(item, provider="searchapi")
    assert listing and listing.price == 24990 and listing.currency == "INR"
    assert listing.retailer_domain == "flipkart.com"


def test_searchapi_amazon_product_adapter():
    payload = {
        "product": {
            "title": "Apple iPhone 17 (256 GB) - Black",
            "brand": "Apple",
            "asin": "B0TEST1234",
            "description": "The iPhone 17.",
            "rating": 4.5,
            "reviews": 1800,
            "main_image": "https://img/main.jpg",
            "images": [{"link": "https://img/1.jpg"}],
            "buybox": {
                "price": {"raw": "₹79,900", "value": 79900, "currency": "INR"},
                "original_price": {"raw": "₹89,900", "value": 89900},
                "fulfillment": {
                    "sold_by": "Appario Retail",
                    "availability": "In stock",
                    "standard_delivery": {"text": "FREE delivery Monday"},
                    "is_prime": True,
                },
            },
            "attributes": [{"name": "Item model number", "value": "MTP03HN/A"}],
        }
    }
    details = normalize_amazon_product(
        adapt_searchapi_product(payload), "B0TEST1234", "amazon.in", provider="searchapi"
    )
    assert details.title.startswith("Apple iPhone 17") and details.brand == "Apple"
    assert details.identifiers["asin"] == "B0TEST1234" and details.identifiers["mpn"] == "MTP03HN/A"
    assert details.images[0] == "https://img/main.jpg"
    offer = details.offers[0]
    assert offer.price == 79900 and offer.original_price == 89900
    assert offer.seller_name == "Appario Retail" and offer.shipping_price == 0.0
    assert offer.availability == "in_stock" and offer.source_provider == "searchapi"
