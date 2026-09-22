"""Photo search must compare, never claim an exact match; a one-offer product must
fetch a comparison on its own page; the fan-out query is short and sane."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.models import Offer
from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.services.product_normalizer import search_query_for

KURTA = (
    "Nermosa Women's Hand Block Floral Printed Straight Kurta Set with Palazzo Pants & "
    "Dupatta Ethnic Kurta Set for Casual Outings Day Events Summer Wear Festive"
)


def _listing(title, retailer, domain, price, **kw):
    return NormalizedListing(
        title=title,
        url=kw.pop("url", f"https://www.{domain}/p/{abs(hash(title + retailer)) % 10**6}"),
        price=price,
        retailer_name=retailer,
        retailer_domain=domain,
        availability="in_stock",
        source_provider="test",
        source_engine="fake",
        **kw,
    )


class FakeLens:
    name = "test"
    engine = "fake_lens"
    enabled = True

    def __init__(self, items):
        self.items = items

    async def search_by_image(self, image_url):
        return ProviderResult(items=list(self.items), provider=self.name, engine=self.engine)


class FakeSearch:
    name = "test"
    engine = "fake_shopping"
    enabled = True

    def __init__(self, items):
        self.items, self.queries = items, []

    async def search_products(self, query, *, max_results=20, min_price=None, max_price=None):
        self.queries.append(query)
        return ProviderResult(items=list(self.items), provider=self.name, engine=self.engine)


class NoAmazon:
    name = "test"
    engine = "fake_amazon"
    enabled = True
    retailer_slug = "amazon-india"

    async def search_retailer(self, query, *, max_results=10):
        return ProviderResult(items=[], provider=self.name, engine=self.engine)


def test_search_query_for_is_short_and_drops_sales_words():
    assert (
        search_query_for("Sony WH-1000XM5 Best Active Noise Cancelling Wireless", "Sony")
        == "sony wh-1000xm5"
    )
    q = search_query_for("Buy Women's White & Blue Floral Block Print Kurta Pant Set - Nermosa")
    assert not q.startswith("buy") and len(q.split()) <= 9, q
    q = search_query_for("Apple iPhone 17 (256 GB) - Black, 6.3-inch display", "Apple")
    assert q.startswith("apple iphone 17") and "256gb" in q.replace(" ", "")


@pytest.mark.asyncio
async def test_photo_search_fans_out_and_never_claims_exact(client, monkeypatch):
    lens_hit = _listing(KURTA, "Amazon.in", "amazon.in", 699)
    fanout = FakeSearch(
        [
            _listing(KURTA, "Myntra", "myntra.com", 749),
            _listing(KURTA, "Flipkart", "flipkart.com", 719),
            _listing("Nermosa Women's Anarkali Kurta Yellow", "Myntra", "myntra.com", 899),
        ]
    )
    monkeypatch.setattr(registry, "image_search_providers", lambda: [FakeLens([lens_hit])])
    monkeypatch.setattr(registry, "product_search_providers", lambda: [fanout])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [NoAmazon()])

    r = await client.post("/api/v1/search", json={"image_url": "https://example.com/photo.jpg"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query_type"] == "image" and body["query"] == KURTA
    # The fan-out happened even though Lens returned a priced match, with a short query.
    assert fanout.queries and len(fanout.queries[0].split()) <= 9 and "nermosa" in fanout.queries[0]
    top = body["results"][0]
    assert "Kurta Set" in top["name"]
    assert {"Amazon.in", "Myntra", "Flipkart"} <= set(top["retailers"]), top
    assert top["lowest_price"] == 699
    # Nothing found from a photo is ever labelled exact.
    for x in body["results"]:
        assert x["match"] is not None and x["match"]["match_type"] != "exact_match", x["match"]
    assert any("look-alikes" in w for w in body["meta"]["warnings"])


@pytest.mark.asyncio
async def test_single_offer_product_fetches_a_comparison_on_its_page(
    client, db, admin_headers, monkeypatch
):
    from app.core.config import get_settings

    # Demo mode never refreshes stored offers; production has a vendor key.
    monkeypatch.setattr(get_settings(), "SERPAPI_API_KEY", "test-key")
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [NoAmazon()])
    monkeypatch.setattr(
        registry,
        "product_search_providers",
        lambda: [FakeSearch([_listing(KURTA, "Amazon.in", "amazon.in", 699)])],
    )
    r = await client.post("/api/v1/search", json={"query": "nermosa kurta set"})
    product_id = r.json()["results"][0]["id"]

    # Fresh single offer: the page must not spend a vendor call yet.
    fresh = FakeSearch([_listing(KURTA, "Myntra", "myntra.com", 749)])
    monkeypatch.setattr(registry, "product_search_providers", lambda: [fresh])
    assert (
        await client.get(f"/api/v1/products/{product_id}/offers", headers=admin_headers)
    ).status_code == 200
    assert fresh.queries == []

    # Forty-five minutes later, one offer is still not a comparison: refresh.
    import uuid

    await db.execute(
        update(Offer)
        .where(Offer.product_id == uuid.UUID(product_id))
        .values(observed_at=datetime.now(timezone.utc) - timedelta(minutes=45))
    )
    await db.commit()
    later = FakeSearch(
        [
            _listing(KURTA, "Myntra", "myntra.com", 749),
            _listing(KURTA, "Flipkart", "flipkart.com", 719),
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [later])
    page = await client.get(f"/api/v1/products/{product_id}/offers", headers=admin_headers)
    assert page.status_code == 200
    assert later.queries and len(later.queries[0].split()) <= 9, later.queries
    retailers = {o["retailer"]["name"] for o in page.json()["offers"]}
    assert {"Amazon.in", "Myntra", "Flipkart"} <= retailers, retailers
