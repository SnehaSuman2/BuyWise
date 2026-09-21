"""Search behaviour shoppers notice: model relevance, link fan-out, vendor outages."""

import pytest

from app.providers import registry
from app.providers.base import (
    NormalizedListing,
    NormalizedProductDetails,
    ProviderResult,
)


def listing(title, retailer, domain, price, **kw):
    return NormalizedListing(
        title=title,
        url=kw.pop("url", f"https://www.{domain}/p/{abs(hash(title + retailer)) % 10**6}"),
        price=price,
        retailer_name=retailer,
        retailer_domain=domain,
        availability="in_stock",
        shipping_price=0.0,
        shipping_known=True,
        source_provider="test",
        source_engine="fake",
        **kw,
    )


class FakeSearch:
    name = "test"
    engine = "fake_shopping"
    enabled = True

    def __init__(self, items=None, error=None):
        self.items, self.error, self.queries = items or [], error, []

    async def search_products(self, query, *, max_results=20, min_price=None, max_price=None):
        self.queries.append(query)
        if self.error:
            return ProviderResult.failure(self.name, self.engine, self.error)
        return ProviderResult(items=list(self.items), provider=self.name, engine=self.engine)


class FakeRetailerSearch:
    name = "test"
    engine = "fake_amazon"
    enabled = True
    retailer_slug = "amazon-india"

    def __init__(self, error=None):
        self.error = error

    async def search_retailer(self, query, *, max_results=10):
        if self.error:
            return ProviderResult.failure(self.name, self.engine, self.error)
        return ProviderResult(items=[], provider=self.name, engine=self.engine)


class FakeAmazonProduct:
    name = "test"
    engine = "fake_amazon_product"
    enabled = True

    def __init__(self, details):
        self.details = details

    async def get_product_details(self, identifier):
        return ProviderResult(items=[self.details], provider=self.name, engine=self.engine)


@pytest.mark.asyncio
async def test_named_model_search_hides_other_generations(client, monkeypatch):
    items = [
        listing("Apple iPhone 17 (256 GB) - Black", "Amazon.in", "amazon.in", 79900),
        listing("Apple iPhone 17 256GB Black", "Flipkart", "flipkart.com", 79490),
        listing("Apple iPhone 16 128GB Blue", "Croma", "croma.com", 64900),
        listing("Apple iPhone 13 (128GB) - Midnight", "Flipkart", "flipkart.com", 42999),
        listing("Apple iPhone 15 (128 GB) - Pink", "Croma", "croma.com", 56900),
        listing("Apple iPhone 17 Pro Max 256GB", "Croma", "croma.com", 149900),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(items)])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])

    r = await client.post("/api/v1/search", json={"query": "iphone 17", "page_size": 24})
    assert r.status_code == 200, r.text
    names = [x["name"] for x in r.json()["results"]]
    assert names, r.json()
    assert not any(("iPhone 16" in n or "iPhone 13" in n or "iPhone 15" in n) for n in names), names
    assert any("iPhone 17" in n for n in names)
    assert any("different model" in w for w in r.json()["meta"]["warnings"])
    # Typed queries show no match badge: the shopper gave no product to match against.
    assert all(x["match"] is None for x in r.json()["results"])

    # A query without a model keeps everything.
    r = await client.post("/api/v1/search", json={"query": "apple iphone", "page_size": 24})
    names = [x["name"] for x in r.json()["results"]]
    assert any("iPhone 16" in n for n in names) and any("iPhone 13" in n for n in names)


@pytest.mark.asyncio
async def test_link_search_attaches_other_retailers_to_the_same_product(client, monkeypatch):
    asin = "B0TEST1234"
    amazon_offer = listing(
        "Apple iPhone 17 (256 GB) - Black",
        "Amazon.in",
        "amazon.in",
        79900,
        url=f"https://www.amazon.in/dp/{asin}",
        identifiers={"asin": asin},
        seller_name="Appario Retail",
    )
    details = NormalizedProductDetails(
        title="Apple iPhone 17 (256 GB) - Black, 6.3-inch display, A19 chip, 48MP camera",
        brand="Apple",
        category="Smartphones",
        images=["https://img/main.jpg"],
        identifiers={"asin": asin},
        offers=[amazon_offer],
        source_provider="test",
        source_engine="fake_amazon_product",
        source_url=f"https://www.amazon.in/dp/{asin}",
    )
    fanout = FakeSearch(
        [
            listing("Apple iPhone 17 256GB Black", "Croma", "croma.com", 78990),
            listing("Apple iPhone 17 256 GB (Black)", "Flipkart", "flipkart.com", 79490),
            listing("Apple iPhone 17 128GB Black", "Croma", "croma.com", 69900),
        ]
    )
    monkeypatch.setattr(registry, "amazon_product_provider", lambda: FakeAmazonProduct(details))
    monkeypatch.setattr(registry, "product_search_providers", lambda: [fanout])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])

    r = await client.post(
        "/api/v1/search", json={"url": f"https://www.amazon.in/dp/{asin}", "page_size": 24}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query_type"] == "url" and body["detected_retailer"] == "Amazon.in"

    # The fan-out query is short and specific, not the retailer's whole title.
    assert fanout.queries and len(fanout.queries[0].split()) <= 8, fanout.queries
    assert "iphone 17" in fanout.queries[0].lower()

    ref_id = body["reference_product_id"]
    ref = next(x for x in body["results"] if x["id"] == ref_id)
    assert {"Amazon.in", "Croma", "Flipkart"} <= set(ref["retailers"]), ref
    assert ref["lowest_price"] == 78990 and ref["offer_count"] >= 3

    # The 128 GB listing is a different variant and must stay its own product.
    others = [x for x in body["results"] if x["id"] != ref_id]
    assert any("128" in x["name"] for x in others), [x["name"] for x in others]
    assert all("Croma" not in x["retailers"] or "128" in x["name"] for x in others)


@pytest.mark.asyncio
async def test_vendor_outage_falls_back_to_catalogue(client, monkeypatch):
    items = [
        listing("Sony WH-1000XM5 Wireless Headphones", "Amazon.in", "amazon.in", 24990),
        listing("Sony WH-1000XM5 Wireless Headphones Black", "Croma", "croma.com", 25990),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(items)])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])
    first = await client.post("/api/v1/search", json={"query": "sony wh-1000xm5"})
    assert first.status_code == 200 and first.json()["results"]

    quota = "serpapi search quota reached"
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(error=quota)])
    monkeypatch.setattr(
        registry, "retailer_search_providers", lambda: [FakeRetailerSearch(error=quota)]
    )
    second = await client.post("/api/v1/search", json={"query": "sony wh-1000xm5"})
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["results"], body
    assert any("temporarily unavailable" in w for w in body["meta"]["warnings"])
    assert body["results"][0]["retailers"]


@pytest.mark.asyncio
async def test_price_bounds_apply_locally(client, monkeypatch):
    items = [
        listing("Sony WH-1000XM5 Wireless Headphones", "Amazon.in", "amazon.in", 24990),
        listing("Sony WH-1000XM5 Wireless Headphones", "Croma", "croma.com", 31990),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(items)])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])
    r = await client.post("/api/v1/search", json={"query": "sony wh-1000xm5", "max_price": 26000})
    assert r.status_code == 200
    for x in r.json()["results"]:
        assert x["lowest_price"] <= 26000


@pytest.mark.asyncio
async def test_listings_without_a_merchant_are_not_results(client, monkeypatch):
    items = [
        listing("Sony WH-1000XM5 Wireless Headphones", "Amazon.in", "amazon.in", 24990),
        NormalizedListing(
            title="Sony WH-1000XM5 Wireless Headphones",
            url="https://www.google.com/shopping/product/1",
            price=9990,
            retailer_name=None,
            retailer_domain=None,
            source_provider="test",
        ),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(items)])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])
    r = await client.post("/api/v1/search", json={"query": "sony wh-1000xm5"})
    assert r.status_code == 200
    for x in r.json()["results"]:
        assert "Unknown retailer" not in x["retailers"]
        assert x["lowest_price"] == 24990


@pytest.mark.asyncio
async def test_outage_shows_one_clear_warning(client, monkeypatch):
    items = [listing("Sony WH-1000XM5 Wireless Headphones", "Amazon.in", "amazon.in", 24990)]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(items)])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])
    await client.post("/api/v1/search", json={"query": "sony wh-1000xm5"})
    quota = "serpapi search quota reached"
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(error=quota)])
    monkeypatch.setattr(
        registry, "retailer_search_providers", lambda: [FakeRetailerSearch(error=quota)]
    )
    body = (await client.post("/api/v1/search", json={"query": "sony wh-1000xm5"})).json()
    outage = [w for w in body["meta"]["warnings"] if "temporarily unavailable" in w]
    assert len(outage) == 1 and "seen before" in outage[0]


def test_fanout_query_prefers_a_literal_model_code():
    from app.services.product_matcher import Candidate
    from app.services.search_service import SearchService

    amazon_title = (
        "Sony WH-1000XM5 Best Active Noise Cancelling Wireless Bluetooth Over Ear "
        "Headphones with Mic for Clear Calling, 30Hrs Battery Life, Black"
    )
    assert SearchService._fanout_query(Candidate(amazon_title, brand="Sony")) == "sony wh-1000xm5"
    iphone = Candidate(
        "Apple iPhone 17 (256 GB) - Black, 6.3-inch display, A19 chip", brand="Apple"
    )
    q = SearchService._fanout_query(iphone)
    assert q.startswith("apple iphone 17") and "256gb" in q.replace(" ", "")
