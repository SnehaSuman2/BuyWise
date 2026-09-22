"""The comparison itself: several stores per product, and the paywall in front of it."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Subscription, User
from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult


def listing(title, retailer, domain, price, **kw):
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


class FakeSearch:
    name, engine, enabled = "test", "fake_shopping", True

    def __init__(self, items):
        self.items, self.queries = items, []

    async def search_products(self, query, *, max_results=20, min_price=None, max_price=None):
        self.queries.append(query)
        return ProviderResult(items=list(self.items), provider=self.name, engine=self.engine)


class FakeAmazon:
    name, engine, enabled, retailer_slug = "test", "fake_amazon", True, "amazon-india"

    def __init__(self, items=None):
        self.items, self.queries = items or [], []

    async def search_retailer(self, query, *, max_results=10):
        self.queries.append(query)
        return ProviderResult(items=list(self.items), provider=self.name, engine=self.engine)


class FakeEnricher:
    """Stands in for Google's 'every store' lookup."""

    name, engine, enabled = "test", "fake_stores", True

    def __init__(self, stores):
        self.stores, self.asked = stores, []

    async def offers_for(self, *, token, product_id):
        self.asked.append((token, product_id))
        return ProviderResult(items=list(self.stores), provider=self.name, engine=self.engine)


@pytest.mark.asyncio
async def test_amazon_is_searched_alongside_google_every_time(client, admin_headers, monkeypatch):
    google = FakeSearch(
        [listing(f"Widget {i} Pro", "Croma", "croma.com", 1000 + i) for i in range(10)]
    )
    amazon = FakeAmazon()
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [amazon])
    r = await client.post("/api/v1/search", headers=admin_headers, json={"query": "widget"})
    assert r.status_code == 200
    # Google returned plenty; Amazon was asked anyway, in the same pass.
    assert amazon.queries == ["widget"]


@pytest.mark.asyncio
async def test_same_product_from_two_stores_groups_without_a_model_code(
    client, admin_headers, monkeypatch
):
    google = FakeSearch(
        [
            listing(
                "Zebronics Pixaplay 35 Smart LED Projector 4K Support",
                "Flipkart",
                "flipkart.com",
                5999,
            )
        ]
    )
    amazon = FakeAmazon(
        [
            listing(
                "ZEBRONICS PIXAPLAY 35 4K Home Theatre Projector 1080p",
                "Amazon.in",
                "amazon.in",
                5799,
            )
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [amazon])
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "zebronics pixaplay 35"}
    )
    results = r.json()["results"]
    assert len(results) == 1, [x["name"] for x in results]
    assert set(results[0]["retailers"]) == {"Flipkart", "Amazon.in"}
    assert results[0]["offer_count"] == 2 and results[0]["lowest_price"] == 5799


@pytest.mark.asyncio
async def test_search_fetches_every_store_for_products_google_flags(
    client, admin_headers, monkeypatch
):
    google = FakeSearch(
        [
            listing(
                "Portronics Beem 440 Smart LED Projector",
                "Flipkart",
                "flipkart.com",
                5099,
                multiple_sources=True,
                enrichment_token="tok-beem-440",
                identifiers={"google_product_id": "gp-440"},
            )
        ]
    )
    stores = FakeEnricher(
        [
            listing("Portronics Beem 440 Smart LED Projector", "Amazon.in", "amazon.in", 4999),
            listing("Portronics Beem 440 Smart LED Projector", "Croma", "croma.com", 5199),
            listing(
                "Portronics Beem 440 Smart LED Projector",
                "Reliance Digital",
                "reliancedigital.in",
                5299,
            ),
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(registry, "offers_enricher", lambda: stores)
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "portronics beem 440"}
    )
    result = r.json()["results"][0]
    assert stores.asked == [("tok-beem-440", "gp-440")]
    assert result["offer_count"] == 4, result
    assert {"Flipkart", "Amazon.in", "Croma", "Reliance Digital"} <= set(result["retailers"])
    assert result["lowest_price"] == 4999

    # Opening the product page does not ask Google again.
    offers = await client.get(f"/api/v1/products/{result['id']}/offers", headers=admin_headers)
    assert offers.json()["total_offers"] == 4 and stores.asked == [("tok-beem-440", "gp-440")]


@pytest.mark.asyncio
async def test_product_page_fetches_every_store_on_first_view(client, admin_headers, monkeypatch):
    google = FakeSearch(
        [
            listing(
                "boAt Cinehead E1 Smart HD Projector",
                "Flipkart",
                "flipkart.com",
                8999,
                multiple_sources=True,
                enrichment_token="tok-e1",
            )
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)  # not at search time
    monkeypatch.setattr(registry, "offers_enricher", lambda: None)
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "boat cinehead e1"}
    )
    product = r.json()["results"][0]
    assert product["offer_count"] == 1

    stores = FakeEnricher(
        [listing("boAt Cinehead E1 Smart HD Projector", "Amazon.in", "amazon.in", 8499)]
    )
    monkeypatch.setattr(registry, "offers_enricher", lambda: stores)
    monkeypatch.setattr(get_settings(), "SERPAPI_API_KEY", "k")  # demo mode never refreshes
    page = await client.get(f"/api/v1/products/{product['id']}/offers", headers=admin_headers)
    assert stores.asked == [("tok-e1", None)]
    assert page.json()["total_offers"] == 2
    assert {o["retailer"]["name"] for o in page.json()["offers"]} == {"Flipkart", "Amazon.in"}


# ------------------------------------------------------------------ the paywall


@pytest.fixture
def paywall(monkeypatch):
    monkeypatch.setattr(get_settings(), "PAYWALL_PRICES", True)


async def _make_pro(db, email, plan="pro_monthly"):
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    db.add(
        Subscription(
            user_id=user.id,
            plan=plan,
            status="active",
            provider="razorpay",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    user.plan = "pro"
    await db.commit()


@pytest.mark.asyncio
async def test_without_pro_no_price_leaves_the_server(client, auth_headers, paywall, demo_product):
    for headers in ({}, auth_headers):
        r = await client.post("/api/v1/search", headers=headers, json={"query": "Sony WH-1000XM5"})
        for x in r.json()["results"]:
            assert x["locked"] is True and x["lowest_price"] is None and x["highest_price"] is None
            assert x["retailers"] == [] and x["offer_count"] == 0
            assert x["hint"] and "Pro" in x["hint"]
        detail = (await client.get(f"/api/v1/products/{demo_product}", headers=headers)).json()
        assert (
            detail["locked"] is True
            and detail["lowest_price"] is None
            and detail["offer_count"] == 0
        )
        offers = (
            await client.get(f"/api/v1/products/{demo_product}/offers", headers=headers)
        ).json()
        assert offers["locked"] is True and offers["offers"] == [] and offers["picks"] == []
        assert offers["lowest_final_price"] is None and offers["hidden_offers"] >= 1
        history = (
            await client.get(f"/api/v1/products/{demo_product}/history?days=90", headers=headers)
        ).json()
        assert history["locked"] is True and history["history"] == [] and history["stats"] is None
        agent = (
            await client.post("/api/v1/agent", headers=headers, json={"query": "sony wh-1000xm5"})
        ).json()
        assert agent["products"] and "₹" not in agent["answer"]
        assert all(
            p["product"]["locked"] and p["product"]["lowest_price"] is None
            for p in agent["products"]
        )
        assert any("part of BuyWise Pro" in w for w in agent["meta"]["warnings"])


@pytest.mark.asyncio
async def test_pro_and_admin_see_prices_behind_the_paywall(
    client, auth_headers, admin_headers, db, paywall, demo_product
):
    await _make_pro(db, "user@buywisetest.com")
    for headers in (auth_headers, admin_headers):
        r = await client.post("/api/v1/search", headers=headers, json={"query": "Sony WH-1000XM5"})
        assert all(not x["locked"] and x["lowest_price"] for x in r.json()["results"])
        offers = (
            await client.get(f"/api/v1/products/{demo_product}/offers", headers=headers)
        ).json()
        assert not offers["locked"] and len(offers["offers"]) >= 2 and offers["picks"]
        history = (
            await client.get(f"/api/v1/products/{demo_product}/history?days=90", headers=headers)
        ).json()
        assert not history["locked"]


def test_free_plan_copy_matches_the_paywall(paywall):
    from app.services.subscription_service import plans

    free = next(p for p in plans() if p.id == "free")
    joined = " ".join(free.features)
    assert "Lowest price" not in joined and "price history" not in joined.lower()
    assert "Trust Scores" in joined


@pytest.mark.asyncio
async def test_slow_store_lookups_do_not_hold_the_search(client, admin_headers, monkeypatch):
    import asyncio

    from app.services.search_service import drain_background_tasks

    class SlowEnricher(FakeEnricher):
        async def offers_for(self, *, token, product_id):
            await asyncio.sleep(0.5)
            return await super().offers_for(token=token, product_id=product_id)

    google = FakeSearch(
        [
            listing(
                "Lifelong LightBeam Plus Smart Projector",
                "Amazon.in",
                "amazon.in",
                7999,
                multiple_sources=True,
                enrichment_token="tok-lb",
            )
        ]
    )
    stores = SlowEnricher(
        [listing("Lifelong LightBeam Plus Smart Projector", "Croma", "croma.com", 7499)]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(registry, "offers_enricher", lambda: stores)
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_WAIT_SECONDS", 0.05)

    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "lifelong lightbeam"}
    )
    product = r.json()["results"][0]
    assert product["offer_count"] == 1  # answered before the slow lookup finished

    await drain_background_tasks()  # the lookup still completes on its own
    page = await client.get(f"/api/v1/products/{product['id']}/offers", headers=admin_headers)
    assert page.json()["total_offers"] == 2
    assert stores.asked == [("tok-lb", None)]
