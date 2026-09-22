"""The curated catalogue: every entry round-trips through the normaliser, the
category page filters by specification, and prices stay behind Pro."""

import pytest

from app.core.config import get_settings
from app.data.catalog_models import CATALOG_MODELS, catalog_model, storage_label
from app.providers import registry
from app.services.product_normalizer import extract_attributes
from tests.test_offers_enrichment_and_paywall import (  # noqa: F401
    FakeAmazon,
    FakeSearch,
    listing,
    paywall,
)


def test_every_catalog_entry_is_recognised_by_the_normaliser():
    seen = set()
    for m in CATALOG_MODELS:
        assert m["line"] not in seen, f"duplicate line {m['line']}"
        seen.add(m["line"])
        assert extract_attributes(m["label"]).line == m["line"], m["label"]
        assert m["specs"]["storage_gb"] == sorted(m["specs"]["storage_gb"])
        assert m["specs"]["display_in"] and m["specs"]["main_camera_mp"]
        assert m["verified_on"]
    assert storage_label(1024) == "1TB" and storage_label(256) == "256GB"
    assert catalog_model("iphone17")["brand"] == "Apple" and catalog_model("nope") is None


def test_plus_and_bracketed_models_are_their_own_lines():
    assert extract_attributes("Samsung Galaxy S25+ 5G (12GB, 256GB)").line == "galaxys25plus"
    assert extract_attributes("Samsung Galaxy S25 5G (12GB, 256GB)").line == "galaxys25"
    assert extract_attributes("Nothing Phone (3a) 5G").line == "nothingphone3a"
    assert (
        extract_attributes("OnePlus Nord 5").line == extract_attributes("Nord 5 5G").line == "nord5"
    )
    assert (
        extract_attributes("Motorola Edge 60 Pro").line
        == extract_attributes("Moto Edge 60 Pro").line
    )


@pytest.mark.asyncio
async def test_category_page_filters_by_spec_and_shows_live_prices(
    client, admin_headers, monkeypatch
):
    google = FakeSearch(
        [
            listing("Apple iPhone 17 (Black, 256 GB)", "Flipkart", "flipkart.com", 79999),
            listing(
                "iPhone 17 256 GB Display with Promotion, A19 Chip, White",
                "Amazon.in",
                "amazon.in",
                82900,
                identifiers={"asin": "B0X1"},
            ),
            listing("Apple iPhone 17 Pro 256GB Deep Blue", "Croma", "croma.com", 134900),
        ]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    await client.post("/api/v1/search", headers=admin_headers, json={"query": "iphone 17"})

    r = await client.get("/api/v1/catalog/phones", headers=admin_headers)
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == len(CATALOG_MODELS) and not page["locked"]
    by_line = {m["line"]: m for m in page["models"]}
    assert by_line["iphone17"]["lowest_price"] == 79999 and by_line["iphone17"]["store_count"] == 2
    assert by_line["iphone17pro"]["lowest_price"] == 134900
    assert by_line["galaxys25"]["lowest_price"] is None and by_line["galaxys25"]["store_count"] == 0
    assert any(f["value"] == "Apple" for f in page["facets"]["brands"])

    r = await client.get(
        "/api/v1/catalog/phones?brand=Samsung&ram=12&storage=1024", headers=admin_headers
    )
    lines = {m["line"] for m in r.json()["models"]}
    assert lines == {"galaxys25ultra", "galaxyzfold7"}, lines

    r = await client.get("/api/v1/catalog/phones?max_screen=6.2", headers=admin_headers)
    lines = {m["line"] for m in r.json()["models"]}
    assert "galaxys25" in lines and "iphone16" in lines and "iphone17promax" not in lines

    r = await client.get(
        "/api/v1/catalog/phones?min_price=80000&max_price=90000", headers=admin_headers
    )
    assert {m["line"] for m in r.json()["models"]} == set(), r.json()["models"]
    r = await client.get(
        "/api/v1/catalog/phones?min_price=70000&max_price=90000&sort=price_asc",
        headers=admin_headers,
    )
    assert [m["line"] for m in r.json()["models"]] == ["iphone17"]

    assert (await client.get("/api/v1/catalog/watches")).status_code == 404
    assert (await client.get("/api/v1/catalog")).json()["categories"][0]["key"] == "phones"


@pytest.mark.asyncio
async def test_category_prices_are_withheld_without_pro(
    client,
    admin_headers,
    paywall,  # noqa: F811
    monkeypatch,
):
    google = FakeSearch(
        [listing("Apple iPhone 17 (Black, 256 GB)", "Flipkart", "flipkart.com", 79999)]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    await client.post("/api/v1/search", headers=admin_headers, json={"query": "iphone 17"})
    page = (await client.get("/api/v1/catalog/phones")).json()
    assert page["locked"]
    card = next(m for m in page["models"] if m["line"] == "iphone17")
    assert card["lowest_price"] is None and card["offer_count"] == 0 and card["store_count"] == 1
    # A price filter cannot be used to infer prices without Pro.
    filtered = (await client.get("/api/v1/catalog/phones?min_price=1&max_price=2")).json()
    assert filtered["total"] == page["total"]


@pytest.mark.asyncio
async def test_family_lists_official_sizes_and_specs(client, admin_headers, monkeypatch):
    google = FakeSearch(
        [listing("Apple iPhone 17 (Black, 256 GB)", "Flipkart", "flipkart.com", 79999)]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    fam = (
        await client.post("/api/v1/search", headers=admin_headers, json={"query": "iphone 17"})
    ).json()["family"]
    assert fam["curated"] and fam["official_storages"] == ["256GB", "512GB"]
    assert fam["specs"]["chip"] == "Apple A19" and "manufacturer" in fam["specs_note"]
    labels = [(v["label"], v["official"], v["offer_count"]) for v in fam["variants"]]
    assert labels == [("256GB", True, 1), ("512GB", True, 0)], labels

    # A curated line nobody has searched yet still has a page: sizes and specs, no stores.
    r = await client.get("/api/v1/products/family?line=pixel9a", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["official_storages"] == ["128GB", "256GB"] and r.json()["total_offers"] == 0


def test_category_queries_are_read_with_their_filters():
    from app.services.catalog_browse import catalog_for_query

    assert catalog_for_query("phone under 20000") == (
        "phones",
        {"brands": [], "max_price": 20000.0},
    )
    assert catalog_for_query("best 5g mobiles under 20k") == (
        "phones",
        {"brands": [], "max_price": 20000.0},
    )
    assert catalog_for_query("samsung phone 8gb ram 256gb") == (
        "phones",
        {"brands": ["Samsung"], "ram_gb": [8], "storage_gb": [256]},
    )
    assert catalog_for_query("iphone") == ("phones", {"brands": ["Apple"]})
    assert catalog_for_query("phones between 30000 and 50000")[1] == {
        "brands": [],
        "min_price": 30000.0,
        "max_price": 50000.0,
    }
    assert catalog_for_query("iphone 17") is None  # a named line: the family answers
    assert catalog_for_query("sony wh-1000xm5") is None
    assert catalog_for_query("wireless headphones") is None


@pytest.mark.asyncio
async def test_category_search_carries_the_spec_panel(client, admin_headers, monkeypatch):
    google = FakeSearch(
        [listing("Apple iPhone 17 (Black, 256 GB)", "Flipkart", "flipkart.com", 79999)]
    )
    monkeypatch.setattr(registry, "product_search_providers", lambda: [google])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeAmazon()])
    monkeypatch.setattr(get_settings(), "SEARCH_ENRICH_LIMIT", 0)
    await client.post("/api/v1/search", headers=admin_headers, json={"query": "iphone 17"})

    body = (
        await client.post(
            "/api/v1/search", headers=admin_headers, json={"query": "apple phone under 90000"}
        )
    ).json()
    assert body["family"] is None and body["catalog"] is not None
    assert body["catalog_filters"] == {"brands": ["Apple"], "max_price": 90000.0}
    assert [m["line"] for m in body["catalog"]["models"]] == [
        "iphone17"
    ]  # the only Apple with a price under 90k

    body = (
        await client.post(
            "/api/v1/search", headers=admin_headers, json={"query": "samsung 12gb ram"}
        )
    ).json()
    lines = {m["line"] for m in body["catalog"]["models"]}
    assert (
        lines
        and all(l.startswith("galaxy") for l in lines)
        and "galaxya56" in lines
        and "galaxys25fe" not in lines
    )

    # A named line gets the family, not the catalogue panel.
    body = (
        await client.post("/api/v1/search", headers=admin_headers, json={"query": "iphone 17"})
    ).json()
    assert body["family"] is not None and body["catalog"] is None
