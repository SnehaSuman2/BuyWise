"""Batched persistence keeps behaviour identical while cutting database round trips."""

import pytest
from sqlalchemy import func, select

from app.models import Offer, PriceHistory
from app.services import catalog


@pytest.mark.asyncio
async def test_price_history_is_written_for_batched_offers(client, db, demo_product):
    import uuid

    pid = uuid.UUID(demo_product)
    offers = (
        await db.execute(select(func.count()).select_from(Offer).where(Offer.product_id == pid))
    ).scalar_one()
    history = (
        await db.execute(
            select(func.count()).select_from(PriceHistory).where(PriceHistory.product_id == pid)
        )
    ).scalar_one()
    assert offers >= 1 and history >= 1
    # every history row points at a flushed offer id
    orphan = (
        await db.execute(
            select(func.count()).select_from(PriceHistory).where(PriceHistory.offer_id.is_(None))
        )
    ).scalar_one()
    assert orphan == 0


@pytest.mark.asyncio
async def test_load_offers_many_matches_per_product_loads(client, db, demo_product):
    import uuid

    pid = uuid.UUID(demo_product)
    single = await catalog.load_offers(db, pid)
    many = await catalog.load_offers_many(db, {pid, uuid.uuid4()})
    assert [o.id for o in many[pid]] == [o.id for o in single]
    assert many[next(k for k in many if k != pid)] == []


@pytest.mark.asyncio
async def test_retailer_list_counts_agree_with_detail(client, demo_product):
    """The list reports stored scores only; the detail page computes a baseline on
    first view. So view details first, then the list must agree with them."""
    listing = await client.get("/api/v1/retailers")
    assert listing.status_code == 200 and listing.json()
    with_offers = [r for r in listing.json() if r["total_offers"]]
    assert with_offers
    details = {}
    for r in with_offers[:3]:
        detail = await client.get(f"/api/v1/retailers/{r['id']}")
        assert detail.status_code == 200
        details[r["id"]] = detail.json()
    listing = {r["id"]: r for r in (await client.get("/api/v1/retailers")).json()}
    for rid, d in details.items():
        assert listing[rid]["total_offers"] == d["total_offers"]
        assert listing[rid]["trust_score"] == d["trust_score"]
