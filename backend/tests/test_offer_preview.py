"""Public previews must not expose the recommended retailers or their prices."""

from datetime import datetime, timezone

import pytest

from app.core.config import get_settings
from app.models import Offer, Product, Retailer
from app.services.offer_service import OfferService


async def make_product(db, count=7):
    product = Product(name="Preview headphones", is_demo=True)
    db.add(product)
    await db.flush()
    retailers = []
    for i in range(count):
        retailer = Retailer(
            name=f"Preview Store {i}", slug=f"preview-{i}", domain=f"preview-{i}.in"
        )
        db.add(retailer)
        await db.flush()
        retailers.append(retailer)
        db.add(
            Offer(
                product_id=product.id,
                retailer_id=retailer.id,
                product_url=f"https://preview-{i}.in/item",
                listed_price=10000 + i * 100,
                estimated_final_price=10000 + i * 100,
                match_type="exact_match",
                match_confidence=1,
                availability="in_stock",
                condition="new",
                observed_at=datetime.now(timezone.utc),
                source_provider="test",
                is_demo=True,
            )
        )
    await db.commit()
    return product, retailers


@pytest.mark.asyncio
@pytest.mark.parametrize("prices_locked", [True, False])
async def test_preview_excludes_winners_duplicates_ties_and_unavailable_offers(
    client, db, auth_headers, admin_headers, monkeypatch, prices_locked
):
    monkeypatch.setattr(get_settings(), "PAYWALL_PRICES", prices_locked)
    product, retailers = await make_product(db)
    # Neither a duplicate of the winning retailer nor another tied lowest price
    # may provide a back door into the paid results.
    for retailer, price, match, availability in [
        (retailers[0], 10001, "exact_match", "in_stock"),
        (retailers[5], 10000, "exact_match", "in_stock"),
        (retailers[6], 10002, "same_product_different_variant", "in_stock"),
        (retailers[6], 10003, "exact_match", "out_of_stock"),
    ]:
        db.add(
            Offer(
                product_id=product.id,
                retailer_id=retailer.id,
                product_url=f"https://{retailer.domain}/extra-{price}",
                listed_price=price,
                estimated_final_price=price,
                match_type=match,
                match_confidence=1,
                availability=availability,
                condition="new",
                observed_at=datetime.now(timezone.utc),
                source_provider="test",
                is_demo=True,
            )
        )
    await db.commit()
    url = f"/api/v1/products/{product.id}/offers"
    full = (await client.get(url, headers=admin_headers)).json()
    assert not full["locked"] and full["picks"] and full["locked_pick_categories"] == []
    picked_ids = {p["offer_id"] for p in full["picks"]}
    protected = {o["retailer"]["id"] for o in full["offers"] if o["id"] in picked_ids}
    bodies = []
    for headers in ({}, auth_headers):
        response = await client.get(url, headers=headers)
        assert response.status_code == 200
        body = response.json()
        bodies.append(body)
        assert body["locked"] and len(body["offers"]) == 2
        assert body["picks"] == [] and body["lowest_final_price"] is None
        assert "CHEAPEST" in body["locked_pick_categories"]
        assert body["hidden_offers"] == full["total_offers"] - 2
        assert len({o["retailer"]["id"] for o in body["offers"]}) == 2
        for offer in body["offers"]:
            assert offer["retailer"]["id"] not in protected
            assert offer["price"]["estimated_final_price"] > full["lowest_final_price"]
            assert offer["match"]["match_type"] == "exact_match"
            assert offer["availability"] != "out_of_stock"
        for offer in full["offers"]:
            if offer["retailer"]["id"] in protected:
                assert offer["retailer"]["id"] not in response.text
                assert offer["product_url"] not in response.text
    assert bodies[0] == bodies[1]
    # Other service consumers do not implicitly get preview access.
    restricted = await OfferService(db).compare(product.id, full=False, prices=False)
    assert restricted.offers == [] and restricted.lowest_final_price is None


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 2])
async def test_sparse_catalogues_do_not_invent_preview_offers(client, db, count, monkeypatch):
    async def no_refresh(self, product):
        return {"providers": [], "warnings": []}

    monkeypatch.setattr(OfferService, "refresh_offers", no_refresh)
    product, _ = await make_product(db, count)
    body = (await client.get(f"/api/v1/products/{product.id}/offers")).json()
    assert body["total_offers"] == count
    assert len(body["offers"]) == max(count - 1, 0)
    assert body["picks"] == [] and body["lowest_final_price"] is None
    assert body["hidden_offers"] == min(count, 1)
    assert body["locked"] is (count > 0)
