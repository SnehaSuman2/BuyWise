"""Plan tiers: what each unlocks, and that the comparison gate lives on the server."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Subscription, User
from app.services.subscription_service import tier


def test_each_tier_unlocks_more_than_the_one_below():
    free, m, h, y = tier("free"), tier("pro_monthly"), tier("pro_6month"), tier("pro_yearly")
    assert free.alerts == 1 and free.saved_products == 3 and free.history_days == 30
    assert not free.compare_offers
    for lower, higher in ((free, m), (m, h), (h, y)):
        assert higher.alerts > lower.alerts
        assert higher.saved_products > lower.saved_products
        assert higher.history_days > lower.history_days
    assert m.compare_offers and h.compare_offers and y.compare_offers
    assert tier("nonsense") == free


async def _make_pro(db, email: str, plan: str) -> None:
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
async def test_visitors_get_the_lowest_price_but_not_the_comparison(client, demo_product):
    r = await client.get(f"/api/v1/products/{demo_product}/offers")
    assert r.status_code == 200
    body = r.json()
    assert body["locked"] is True
    assert len(body["offers"]) == 1, "only the cheapest offer is sent"
    assert body["picks"] == []
    assert body["lowest_final_price"] == body["offers"][0]["price"]["estimated_final_price"]
    assert body["hidden_offers"] >= 1 and body["total_offers"] == body["hidden_offers"] + 1

    recs = await client.get(f"/api/v1/products/{demo_product}/recommendations")
    assert recs.status_code == 200
    assert recs.json()["locked"] is True and recs.json()["recommendations"] == []


@pytest.mark.asyncio
async def test_free_accounts_are_gated_too(client, auth_headers, demo_product):
    r = await client.get(f"/api/v1/products/{demo_product}/offers", headers=auth_headers)
    assert r.json()["locked"] is True and len(r.json()["offers"]) == 1


@pytest.mark.asyncio
async def test_pro_accounts_see_everything(client, auth_headers, db, demo_product):
    await _make_pro(db, "user@buywisetest.com", "pro_monthly")
    r = await client.get(f"/api/v1/products/{demo_product}/offers", headers=auth_headers)
    body = r.json()
    assert body["locked"] is False and body["hidden_offers"] == 0
    assert len(body["offers"]) == body["total_offers"] >= 2
    assert body["picks"], "picks come back for Pro"
    recs = await client.get(
        f"/api/v1/products/{demo_product}/recommendations", headers=auth_headers
    )
    assert recs.json()["locked"] is False and recs.json()["recommendations"]

    status = await client.get("/api/v1/subscription", headers=auth_headers)
    assert status.json()["features"]["compare_offers"] is True
    assert status.json()["limits"]["alerts"] == tier("pro_monthly").alerts


@pytest.mark.asyncio
async def test_admins_see_everything_without_paying(client, admin_headers, demo_product):
    r = await client.get(f"/api/v1/products/{demo_product}/offers", headers=admin_headers)
    assert r.json()["locked"] is False


@pytest.mark.asyncio
async def test_limits_follow_the_tier(client, auth_headers, db, demo_product):
    # Free: one alert, then the door closes.
    first = await client.post(
        "/api/v1/alerts",
        headers=auth_headers,
        json={"product_id": demo_product, "alert_type": "target_price", "target_price": 1},
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/v1/alerts",
        headers=auth_headers,
        json={"product_id": demo_product, "alert_type": "target_price", "target_price": 2},
    )
    assert second.status_code == 402

    # Six-month Pro: the same account can now hold many more.
    await _make_pro(db, "user@buywisetest.com", "pro_6month")
    status = await client.get("/api/v1/subscription", headers=auth_headers)
    assert status.json()["limits"]["alerts"] == tier("pro_6month").alerts
    third = await client.post(
        "/api/v1/alerts",
        headers=auth_headers,
        json={"product_id": demo_product, "alert_type": "target_price", "target_price": 3},
    )
    assert third.status_code == 201, third.text


@pytest.mark.asyncio
async def test_agent_gives_the_price_but_not_the_picks_to_free_users(client, auth_headers, db):
    r = await client.post("/api/v1/agent", json={"query": "sony wh-1000xm5"})
    assert r.status_code == 200
    body = r.json()
    assert body["products"]
    assert all(p["recommendations"]["locked"] for p in body["products"])
    assert "best overall from" not in body["answer"]
    assert any("Pro" in w for w in body["meta"]["warnings"])

    await _make_pro(db, "user@buywisetest.com", "pro_yearly")
    r = await client.post("/api/v1/agent", headers=auth_headers, json={"query": "sony wh-1000xm5"})
    body = r.json()
    assert not any(p["recommendations"]["locked"] for p in body["products"])
    assert not any("part of BuyWise Pro" in w for w in body["meta"]["warnings"])
