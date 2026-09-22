"""Authentication, authorization isolation, alerts, saved products, account deletion."""

import pytest

from app.services.alert_service import AlertService


@pytest.mark.asyncio
async def test_register_login_refresh_rotation(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": "a@buywisetest.com", "username": "abc", "password": "Passw0rd!x"},
    )
    assert r.status_code == 201
    weak = await client.post(
        "/api/v1/auth/register",
        json={"email": "c@buywisetest.com", "username": "cde", "password": "password"},
    )
    assert weak.status_code == 422
    dup = await client.post(
        "/api/v1/auth/register",
        json={"email": "a@buywisetest.com", "username": "zzz", "password": "Passw0rd!x"},
    )
    assert dup.status_code == 409
    bad = await client.post(
        "/api/v1/auth/login", json={"email": "a@buywisetest.com", "password": "wrong-pass1"}
    )
    assert bad.status_code == 401
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "a@buywisetest.com", "password": "Passw0rd!x"}
    )
    assert ok.status_code == 200
    refresh = ok.json()["refresh_token"]
    r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r1.status_code == 200
    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert reuse.status_code == 401  # rotated
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {r1.json()['access_token']}"}
    )
    assert me.status_code == 200 and "password_hash" not in me.text


@pytest.mark.asyncio
async def test_logout_all_invalidates_access_tokens(client, auth_headers):
    r = await client.post("/api/v1/auth/logout-all", headers=auth_headers)
    assert r.status_code == 204
    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_alerts_are_private_and_limited(client, auth_headers, demo_product):
    from app.services.subscription_service import tier

    free_limit = tier("free").alerts
    assert (await client.get("/api/v1/alerts")).status_code == 401
    for _ in range(free_limit):
        r = await client.post(
            "/api/v1/alerts",
            json={"product_id": demo_product, "alert_type": "target_price", "target_price": 100},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
    over = await client.post(
        "/api/v1/alerts",
        json={"product_id": demo_product, "alert_type": "percent_drop", "drop_percent": 10},
        headers=auth_headers,
    )
    assert over.status_code == 402
    mine = await client.get("/api/v1/alerts", headers=auth_headers)
    assert len(mine.json()) == free_limit
    other = await client.post(
        "/api/v1/auth/register",
        json={"email": "o@buywisetest.com", "username": "other", "password": "Passw0rd!x"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert (await client.get("/api/v1/alerts", headers=other_headers)).json() == []
    alert_id = mine.json()[0]["id"]
    assert (
        await client.delete(f"/api/v1/alerts/{alert_id}", headers=other_headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
    ).status_code == 204


@pytest.mark.asyncio
async def test_alert_check_triggers_and_records_notification(
    client, db, auth_headers, demo_product
):
    r = await client.post(
        "/api/v1/alerts",
        json={"product_id": demo_product, "alert_type": "target_price", "target_price": 10_000_000},
        headers=auth_headers,
    )
    assert r.status_code == 201
    result = await AlertService(db).check_all(notify=True)
    assert result["checked"] >= 1 and result["triggered"] >= 1 and result["notified"] >= 1
    await db.commit()
    dash = await client.get("/api/v1/dashboard", headers=auth_headers)
    data = dash.json()
    assert data["price_drops"] and data["notifications"][0]["kind"] == "price_alert"
    assert data["notifications"][0]["status"] in (
        "skipped",
        "sent",
    )  # console email provider in tests


def test_percent_drop_logic():
    from app.models import PriceAlert

    a = PriceAlert(alert_type="percent_drop", drop_percent=10, baseline_price=1000)
    assert AlertService.should_trigger(a, 900) and not AlertService.should_trigger(a, 901)
    b = PriceAlert(alert_type="target_price", target_price=500)
    assert AlertService.should_trigger(b, 500) and not AlertService.should_trigger(b, 501)


@pytest.mark.asyncio
async def test_saved_products_and_account_deletion(client, auth_headers, demo_product):
    r = await client.post(
        "/api/v1/saved-products",
        json={"product_id": demo_product, "note": "gift"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    saved = await client.get("/api/v1/saved-products", headers=auth_headers)
    assert len(saved.json()) == 1 and saved.json()[0]["note"] == "gift"
    bad = await client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirm": "nope", "password": "Passw0rd!x"},
        headers=auth_headers,
    )
    assert bad.status_code == 422
    ok = await client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirm": "DELETE", "password": "Passw0rd!x"},
        headers=auth_headers,
    )
    assert ok.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=auth_headers)).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "user@buywisetest.com", "password": "Passw0rd!x"}
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_admin_protection(client, auth_headers, admin_headers):
    assert (await client.get("/api/v1/admin/status")).status_code == 401
    assert (await client.get("/api/v1/admin/status", headers=auth_headers)).status_code == 403
    r = await client.get("/api/v1/admin/status", headers=admin_headers)
    assert r.status_code == 200 and r.json()["providers"]["data_mode"] == "demo"
    assert "SERPAPI_API_KEY" not in r.text and "secret" not in r.text.lower()
