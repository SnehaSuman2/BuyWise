"""A search writes its products, sellers and history purges in a few statements,
and a slow or failing store lookup does not make the next search wait again."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import Product, Seller
from app.providers import registry
from app.services import catalog
from app.services.offer_service import OfferService
from app.services.search_service import drain_background_tasks
from tests.test_offers_enrichment_and_paywall import FakeAmazon, FakeEnricher, FakeSearch, listing


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_batch_creates_each_product_once_and_reuses_it(
    client, db, admin_headers, monkeypatch
):
    """Two listings for the same product in one search share one product row,
    even though products are now created without flushing between groups."""
    google = FakeSearch(
        [
            listing("Sony WH-1000XM5 Wireless Headphones", "Croma", "croma.com", 24990),
            listing("Sony WH-1000XM5 Wireless Headphones Black", "Flipkart", "flipkart.com", 23990),
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    before = await _count(db, Product)
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "sony wh-1000xm5"}
    )
    assert r.status_code == 200
    xm5 = [x for x in r.json()["results"] if "1000XM5" in x["name"].upper()]
    assert len(xm5) == 1 and xm5[0]["offer_count"] >= 2, r.json()["results"]
    assert await _count(db, Product) == before + 1

    # The same search again finds the product instead of creating another.
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "sony wh-1000xm5"}
    )
    assert r.status_code == 200
    assert await _count(db, Product) == before + 1


@pytest.mark.asyncio
async def test_concurrent_insert_falls_back_to_single_writes(
    client, db, admin_headers, monkeypatch
):
    """If the batch prefetch misses a product another request just created, the
    batched insert conflicts and the search still succeeds without a duplicate."""
    google = FakeSearch([listing("JBL Flip 6 Bluetooth Speaker", "Croma", "croma.com", 9999)])
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    r = await client.post("/api/v1/search", headers=admin_headers, json={"query": "jbl flip 6"})
    assert r.status_code == 200
    count = await _count(db, Product)

    async def blind_prefetch(_db, _wanted):
        return catalog.Prefetched()  # as if the row appeared after we looked

    monkeypatch.setattr(catalog, "prefetch_products", blind_prefetch)
    r = await client.post("/api/v1/search", headers=admin_headers, json={"query": "jbl flip 6"})
    assert r.status_code == 200
    assert [x for x in r.json()["results"] if "FLIP 6" in x["name"].upper()]
    assert await _count(db, Product) == count


@pytest.mark.asyncio
async def test_sellers_are_created_once_without_a_flush_each(
    client, db, admin_headers, monkeypatch
):
    google = FakeSearch(
        [
            listing("Boat Airdopes 141", "Amazon.in", "amazon.in", 1099, seller_name="Cloudtail"),
            listing(
                "Boat Airdopes 141 TWS", "Amazon.in", "amazon.in", 1199, seller_name="Cloudtail"
            ),
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "boat airdopes 141"}
    )
    assert r.status_code == 200
    rows = (await db.execute(select(Seller).where(Seller.name == "Cloudtail"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_history_purge_runs_once_for_the_batch(db, demo_product):
    product = await catalog.load_product(db, uuid.UUID(demo_product))
    offers = await catalog.load_offers(db, product.id)
    retirement = catalog.Retirement(remaining=offers, retired=[], floor=1.0)
    other = catalog.Retirement(remaining=[], retired=[], floor=None)
    assert (
        await catalog.purge_implausible_history_many(db, [(product, retirement), (product, other)])
        == 0
    )


@pytest.mark.asyncio
async def test_failed_store_lookup_is_not_retried_on_every_search(
    client, admin_headers, monkeypatch
):
    class FailingEnricher(FakeEnricher):
        def __init__(self):
            super().__init__([])
            self.calls = 0

        async def offers_for(self, token=None, product_id=None):
            self.calls += 1
            raise RuntimeError("vendor down")

    google = FakeSearch(
        [
            listing(
                "Zebronics Zeb-PixaPlay 35 Projector",
                "Flipkart",
                "flipkart.com",
                6999,
                multiple_sources=True,
                enrichment_token="tok-pixaplay-35",
            )
        ]
    )
    stores = FailingEnricher()
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(registry, "offers_enricher", lambda: stores)
    for _ in range(3):
        r = await client.post(
            "/api/v1/search", headers=admin_headers, json={"query": "pixaplay 35"}
        )
        assert r.status_code == 200
        await drain_background_tasks()
    assert stores.calls == 1

    # Opening the product page does not ask again either, until the retry interval passes.
    pid = r.json()["results"][0]["id"]
    page = await client.get(f"/api/v1/products/{pid}/offers", headers=admin_headers)
    assert page.status_code == 200 and stores.calls == 1


def test_enrichment_attempt_window():
    now = datetime.now(timezone.utc)
    recent = {"enrich_attempted_at": (now - timedelta(minutes=5)).isoformat()}
    old = {"enrich_attempted_at": (now - timedelta(hours=2)).isoformat()}
    assert OfferService.enrichment_attempted_recently(recent, timedelta(minutes=30))
    assert not OfferService.enrichment_attempted_recently(old, timedelta(minutes=30))
    assert not OfferService.enrichment_attempted_recently({}, timedelta(minutes=30))
    assert not OfferService.enrichment_attempted_recently(
        {"enrich_attempted_at": "junk"}, timedelta(minutes=30)
    )


@pytest.mark.asyncio
async def test_every_shop_photo_is_kept_not_just_the_first(client, db, admin_headers, monkeypatch):
    """Each shop publishes its own picture of the same item; together they are a
    gallery. Only the first used to be stored and the rest were discarded."""
    google = FakeSearch(
        [
            listing(
                "Bose QuietComfort Ultra Headphones Black",
                "Croma",
                "croma.com",
                29990,
                image_url="https://img.croma/qc-ultra-front.jpg",
            ),
            listing(
                "Bose QuietComfort Ultra Headphones Black",
                "Flipkart",
                "flipkart.com",
                28990,
                image_url="https://img.flipkart/qc-ultra-side.jpg",
            ),
            listing(
                "Bose QuietComfort Ultra Headphones Black",
                "Vijay Sales",
                "vijaysales.com",
                30990,
                image_url="https://img.croma/qc-ultra-front.jpg",  # the same photo again
            ),
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "bose quietcomfort ultra"}
    )
    assert r.status_code == 200, r.text
    card = next(x for x in r.json()["results"] if "Ultra" in x["name"])
    product = await catalog.load_product(db, uuid.UUID(card["id"]))
    assert product is not None
    assert product.images == [
        "https://img.croma/qc-ultra-front.jpg",
        "https://img.flipkart/qc-ultra-side.jpg",
    ], product.images


def test_image_list_is_deduped_bounded_and_http_only():
    from app.services.catalog import MAX_PRODUCT_IMAGES, dedupe_images

    assert dedupe_images(["https://a/1.jpg", "https://a/1.jpg", None, "", "https://a/2.jpg"]) == [
        "https://a/1.jpg",
        "https://a/2.jpg",
    ]
    # Nothing that is not a fetchable image URL may reach the page.
    assert dedupe_images(["data:image/png;base64,xxx", "/local/path.jpg", 42]) == []
    assert len(dedupe_images([f"https://a/{i}.jpg" for i in range(20)])) == MAX_PRODUCT_IMAGES
    # The hero must not move when another shop turns up later.
    assert dedupe_images(["https://a/1.jpg", "https://a/9.jpg"])[0] == "https://a/1.jpg"
