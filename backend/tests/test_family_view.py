"""A search that names a product line answers with the line's storage sizes,
colours and every store's price in one place, and keeps look-alikes out."""

import pytest

from app.core.config import get_settings
from app.providers import registry
from app.services.family_service import family_for_query, is_family_member
from app.services.product_normalizer import extract_attributes
from tests.test_offers_enrichment_and_paywall import (  # noqa: F401
    FakeAmazon,
    FakeSearch,
    listing,
    paywall,
)


def test_lines_are_read_from_titles_not_stray_codes():
    a = extract_attributes("Apple iPhone 17 (Black, 256 GB) A3258")
    assert (a.line, a.line_label, a.model, a.storage) == (
        "iphone17",
        "iPhone 17",
        "iphone17",
        "256GB",
    )
    assert (
        extract_attributes("iPhone Air 256 GB: Thinnest iPhone Ever, Powerful A19 Pro").line
        == "iphoneair"
    )
    assert extract_attributes("Genuine Apple iPhone 17 Air 5G 256GB/512GB/1TB").line == "iphoneair"
    assert (
        extract_attributes("Galaxy S25 Ultra 5G (Titanium Whitesilver, 12GB RAM, 256GB)").line_label
        == "Galaxy S25 Ultra"
    )
    assert (
        extract_attributes("OnePlus 13R 5G (Nebula Noir, 12GB RAM, 256GB)").line_label
        == "OnePlus 13R"
    )
    assert extract_attributes("iPhone 17 Pro Max case").line == "iphone17promax"
    assert extract_attributes("Sony WH-1000XM5 Wireless Headphones").line is None


def test_services_and_catalogue_listings_are_not_products():
    assert extract_attributes("USA AT&T iPhone 17 (Active Line) – Fast Service").is_service
    assert extract_attributes(
        "Unlocked 5g Smart Phone for I Phone 17 Pro Max 17 air 17 Pro 17"
    ).is_catalogue
    assert extract_attributes(
        "Refurbished Apple iPhone 17 Pro Max eSIM | 256GB 512GB 1TB 2TB"
    ).is_catalogue
    menu = extract_attributes("Genuine Apple iPhone 17 Air 5G 256GB/512GB/1TB")
    assert menu.storage is None and menu.ram is None
    assert not extract_attributes(
        "iPhone 17 256 GB: Display with Promotion, A19 Chip, Black"
    ).is_service
    assert not is_family_member(
        extract_attributes("Full Body Housing for Apple iPhone 17 Pro"), "iphone17pro"
    )
    assert is_family_member(
        extract_attributes("Apple iPhone 17 Pro 256GB Deep Blue"), "iphone17pro"
    )


def test_family_is_named_only_for_line_queries():
    assert family_for_query("iphone 17") == ("iphone17", "iPhone 17", None)
    assert family_for_query("iphone 17 256gb") == ("iphone17", "iPhone 17", "256GB")
    assert family_for_query("iphone 17 case") is None
    assert family_for_query("wireless headphones") is None


def _iphone_world():
    google = FakeSearch(
        [
            listing(
                "iPhone 17 256 GB: 15.93 cm Display, A19 Chip, Black",
                "Amazon.in",
                "amazon.in",
                82900,
                identifiers={"asin": "B0A"},
            ),
            listing(
                "iPhone 17 256 GB: 15.93 cm Display, A19 Chip, White",
                "Amazon.in",
                "amazon.in",
                82900,
                identifiers={"asin": "B0B"},
            ),
            listing("Apple iPhone 17 (Black, 256 GB)", "Flipkart", "flipkart.com", 79999),
            listing("Apple iPhone 17 (256 GB) Lavender", "Croma", "croma.com", 81900),
            listing("Apple iPhone 17 512GB Sage", "Vijay Sales", "vijaysales.com", 102900),
            listing(
                "iPhone Air 256 GB: Thinnest iPhone Ever",
                "Amazon.in",
                "amazon.in",
                119900,
                identifiers={"asin": "B0C"},
            ),
            listing(
                "Galaxy S25 Ultra 5G (Titanium, 12GB RAM, 256GB)",
                "Amazon.in",
                "amazon.in",
                99999,
                identifiers={"asin": "B0D"},
            ),
            listing("Apple iPhone 17 Pro 256GB Deep Blue", "Flipkart", "flipkart.com", 134900),
            listing(
                "USA AT&T iPhone 17 (Active Line) – Fast Service",
                "Baba Tools",
                "babatools.in",
                2149,
            ),
            listing(
                "Unlocked 5g Smart Phone for I Phone 17 Pro Max 17 air 17 Pro 17",
                "Dial4Trade",
                "dial4trade.com",
                50000,
            ),
        ]
    )
    return google


@pytest.mark.asyncio
async def test_line_search_returns_one_family_with_every_store(client, admin_headers, monkeypatch):
    monkeypatch.setattr(registry, "product_search_providers", lambda: [_iphone_world()])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    r = await client.post(
        "/api/v1/search", headers=admin_headers, json={"query": "iphone 17", "page_size": 24}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    names = [x["name"] for x in body["results"]]
    # Other families and generations are gone; the 17 Pro is a sibling card.
    assert not any("Galaxy" in n or "Air" in n or "Service" in n or "Dial" in n for n in names), (
        names
    )
    assert all("iPhone 17" in n for n in names), names
    assert any("Pro" in n for n in names), names

    fam = body["family"]
    assert fam is not None and fam["label"] == "iPhone 17" and not fam["locked"]
    by_storage = {v["storage"]: v for v in fam["variants"]}
    assert set(by_storage) == {"256GB", "512GB"}, by_storage.keys()
    v256 = by_storage["256GB"]
    prices = [o["price"] for o in v256["offers"]]
    assert prices == sorted(prices) and prices[0] == 79999
    assert v256["retailer_count"] == 3 and v256["offer_count"] == 4  # two colours, both Amazon
    assert v256["lowest_price"] == 79999 and v256["highest_price"] == 82900
    assert "black" in v256["colors"] and "white" in v256["colors"]
    assert by_storage["512GB"]["offers"][0]["retailer_name"] == "Vijay Sales"
    assert fam["total_retailers"] == 4 and fam["total_offers"] == 5
    assert all(o["go_url"] for v in fam["variants"] for o in v["offers"])

    # The same family stands on its own, by line.
    page = await client.get("/api/v1/products/family?line=iphone17", headers=admin_headers)
    assert page.status_code == 200 and page.json()["total_offers"] == 5
    assert (
        await client.get("/api/v1/products/family?line=galaxyz99", headers=admin_headers)
    ).status_code == 404

    # A product of the line points back at its family.
    pid = body["results"][0]["id"]
    detail = await client.get(f"/api/v1/products/{pid}", headers=admin_headers)
    assert (
        detail.json()["family_line"] == "iphone17" and detail.json()["family_label"] == "iPhone 17"
    )


@pytest.mark.asyncio
async def test_family_is_locked_without_pro(client, admin_headers, paywall, monkeypatch):  # noqa: F811
    monkeypatch.setattr(registry, "product_search_providers", lambda: [_iphone_world()])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    await client.post("/api/v1/search", headers=admin_headers, json={"query": "iphone 17"})
    r = await client.post("/api/v1/search", json={"query": "iphone 17"})
    fam = r.json()["family"]
    assert fam["locked"] and "with Pro" in fam["hint"]
    assert all(v["offers"] == [] and v["lowest_price"] is None for v in fam["variants"])
    assert fam["total_retailers"] == 4 and fam["variants"][0]["offer_count"] == 4
    assert "store" in fam["hint"] and "4" in fam["hint"]
    page = await client.get("/api/v1/products/family?line=iphone17")
    assert page.json()["locked"] and page.json()["variants"][0]["offers"] == []
