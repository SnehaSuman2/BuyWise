"""Search, offers (true price + match + trust), history, recommendations, agent, affiliate redirect."""

import pytest

from app.services.affiliate_service import build_affiliate_url


@pytest.mark.asyncio
async def test_text_search_demo_labelled(client):
    r = await client.post("/api/v1/search", json={"query": "iphone 15 pro max", "page_size": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["data_mode"] == "demo" and data["meta"]["is_demo"] is True
    names = [x["name"] for x in data["results"]]
    assert any("256 GB" in n for n in names) and any("512 GB" in n for n in names), (
        names
    )  # variants kept separate
    assert all(x["is_demo"] for x in data["results"])


@pytest.mark.asyncio
async def test_search_requires_input_and_rejects_private_urls(client):
    assert (await client.post("/api/v1/search", json={})).status_code == 422
    assert (
        await client.post("/api/v1/search", json={"url": "http://127.0.0.1/health"})
    ).status_code == 422
    assert (
        await client.post("/api/v1/search", json={"url": "http://169.254.169.254/latest/meta-data"})
    ).status_code == 422


@pytest.mark.asyncio
async def test_url_search_reports_match_confidence(client):
    r = await client.post(
        "/api/v1/search",
        json={"url": "https://www.flipkart.com/sony-wh-1000xm5-bluetooth-headset/p/itm123"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["query_type"] == "url" and data["detected_retailer"] == "Flipkart"
    assert data["results"][0]["match"]["match_type"] == "exact_match"
    earbuds = [x for x in data["results"] if "WF-1000XM5" in x["name"]]
    assert all(x["match"]["match_type"] != "exact_match" for x in earbuds)


@pytest.mark.asyncio
async def test_offers_true_price_match_and_trust(client, demo_product):
    r = await client.get(f"/api/v1/products/{demo_product}/offers")
    assert r.status_code == 200
    data = r.json()
    assert data["total_offers"] > 1 and data["picks"]
    cats = {p["category"] for p in data["picks"]}
    assert {"BEST_OVERALL", "CHEAPEST", "SAFEST", "BEST_VALUE"} <= cats
    for o in data["offers"]:
        price = o["price"]
        expected = (
            price["listed_price"] + (price["shipping_price"] or 0) - (price["coupon_amount"] or 0)
        )
        assert abs(price["estimated_final_price"] - expected) < 0.01
        if not price["shipping_known"]:
            assert price["final_price_known"] is False and any(
                "checkout" in n for n in price["notes"]
            )
        assert o["match"]["label"] in ("Exact match", "Possible match")
        assert o["go_url"].endswith(o["id"]) and o["trust"]["risk_level"] in (
            "low",
            "medium",
            "high",
            "unknown",
        )
        assert o["retailer"]["name"] and o["seller"]["name"]


@pytest.mark.asyncio
async def test_history_honest_when_insufficient(client, demo_product):
    r = await client.get(f"/api/v1/products/{demo_product}/history?days=90")
    assert r.status_code == 200
    data = r.json()
    # A fresh search yields one observation per retailer today → not enough history.
    assert data["signal"]["action"] == "INSUFFICIENT_DATA" and "Not enough BuyWise history" in (
        data["message"] or ""
    )
    assert data["stats"] is None or data["stats"]["span_days"] < 7


@pytest.mark.asyncio
async def test_recommendations_and_product_detail(client, demo_product):
    rec = await client.get(f"/api/v1/products/{demo_product}/recommendations")
    assert rec.status_code == 200
    data = rec.json()
    assert data["recommendations"] and data["ai_explanation"] and data["ai_provider"] == "demo"
    assert all(
        r["match_label"] in ("Exact match", "Possible match") for r in data["recommendations"]
    )
    detail = await client.get(f"/api/v1/products/{demo_product}")
    assert (
        detail.status_code == 200
        and detail.json()["offer_count"] >= 1
        and detail.json()["meta"]["data_mode"] == "demo"
    )
    assert (
        await client.get("/api/v1/products/00000000-0000-0000-0000-000000000000")
    ).status_code == 404


@pytest.mark.asyncio
async def test_trust_endpoint_has_evidence_and_explanation(client, demo_product):
    r = await client.get(f"/api/v1/products/{demo_product}/trust")
    assert r.status_code == 200 and r.json()
    t = r.json()[0]
    assert t["explanation"] and t["methodology_version"] and t["evidence_count"] > 0
    rt = await client.get(f"/api/v1/retailers/{t['retailer_id']}/trust")
    assert (
        rt.status_code == 200
        and rt.json()["evidence"]
        and all(e["url"] or e["source"] for e in rt.json()["evidence"])
    )
    # A page view scores curated retailers from their real published policy facts,
    # so the result is genuinely not demo data and must not be labelled as such.
    body = rt.json()
    assert body["meta"]["is_demo"] is False and body["meta"]["data_mode"] == "live"
    assert {e["source"] for e in body["evidence"]} == {"retailer_policy"}
    assert all(e["is_demo"] is False for e in body["evidence"])


@pytest.mark.asyncio
async def test_agent_returns_structured_grounded_answer(client):
    r = await client.post("/api/v1/agent", json={"query": "best wireless headphones under ₹25,000"})
    assert r.status_code == 200
    data = r.json()
    assert data["intent"]["budget_max"] == 25000 and data["products"]
    assert data["meta"]["is_demo"] and "DEMO DATA" in data["answer"]
    for p in data["products"]:
        assert p["product"]["lowest_price"] is None or p["product"]["lowest_price"] <= 25000
    t = await client.post("/api/v1/agent", json={"query": "Is Amazon trustworthy?"})
    assert (
        t.json()["intent"]["kind"] == "seller_trust"
        and t.json()["trust"]["subject_name"] == "Amazon.in"
    )


@pytest.mark.asyncio
async def test_affiliate_redirect_records_click(client, demo_product):
    offers = (await client.get(f"/api/v1/products/{demo_product}/offers")).json()["offers"]
    r = await client.get(f"/api/v1/go/{offers[0]['id']}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://")


def test_affiliate_url_building(monkeypatch):
    from app.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "AMAZON_AFFILIATE_TAG", "buywise-21")
    url, program = build_affiliate_url("https://www.amazon.in/dp/B0X?th=1", "amazon-india")
    assert "tag=buywise-21" in url and "th=1" in url and program == "amazon_associates"
    plain, none = build_affiliate_url("https://www.croma.com/x", "croma")
    assert plain == "https://www.croma.com/x" and none is None
    assert build_affiliate_url(None, "amazon-india") == (None, None)


@pytest.mark.asyncio
async def test_page_endpoints_never_gather_evidence_inline(client, demo_product, monkeypatch):
    """Product and retailer pages must read stored trust only.

    Collecting evidence inline fired a SerpApi burst per merchant and pushed the
    product page past its timeout. Anything a visitor loads must stay off the network.
    """
    from app.services.trust_service import TrustService

    calls = []

    async def _boom(self, retailer):
        calls.append(retailer.slug)
        raise AssertionError(f"refresh_evidence called inline for {retailer.slug}")

    monkeypatch.setattr(TrustService, "refresh_evidence", _boom)

    trust = await client.get(f"/api/v1/products/{demo_product}/trust")
    assert trust.status_code == 200, trust.text

    retailers = await client.get("/api/v1/retailers")
    assert retailers.status_code == 200
    for r in retailers.json()[:3]:
        assert (await client.get(f"/api/v1/retailers/{r['id']}")).status_code == 200
        assert (await client.get(f"/api/v1/retailers/{r['id']}/trust")).status_code in (200, 404)

    assert calls == []
