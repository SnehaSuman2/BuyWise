"""The agent must search for the product the shopper named, model number included."""

import pytest

from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.services.shopping_agent import heuristic_intent


def test_model_numbers_survive_intent_parsing():
    assert heuristic_intent("iphone 17").product_query == "iphone 17"
    i = heuristic_intent("should i buy ihpone 17 rigth now or should i wait")
    assert i.kind == "buy_timing" and i.product_query == "iphone 17", i
    i = heuristic_intent("best place to buy iphone 17 right now")
    assert i.kind == "where_to_buy" and i.product_query == "iphone 17", i
    i = heuristic_intent("sony wh-1000xm5 vs bose qc45")
    assert i.kind == "compare" and i.compare_items == ["sony wh-1000xm5", "bose qc45"], i


def test_budget_is_still_removed_from_the_query():
    i = heuristic_intent("best wireless headphones under ₹25,000")
    assert i.budget_max == 25000 and i.product_query == "wireless headphones", i
    i = heuristic_intent("samsung galaxy s25 ultra under 1.2 lakh")
    assert i.budget_max == 120000 and i.product_query == "samsung galaxy s25 ultra", i
    i = heuristic_intent("laptop under 60k")
    assert i.budget_max == 60000 and i.product_query == "laptop", i


def _listing(title, retailer, domain, price):
    return NormalizedListing(
        title=title,
        url=f"https://www.{domain}/p/{abs(hash(title + retailer)) % 10**6}",
        price=price,
        retailer_name=retailer,
        retailer_domain=domain,
        availability="in_stock",
        source_provider="test",
        source_engine="fake",
    )


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


@pytest.mark.asyncio
async def test_agent_answers_about_the_generation_asked_for(client, monkeypatch):
    items = [
        _listing("Apple iPhone 17 (256 GB) - Black", "Amazon.in", "amazon.in", 79900),
        _listing("Apple iPhone 17 256GB Black", "Flipkart", "flipkart.com", 79490),
        _listing("Apple iPhone 17 256 GB Black", "Croma", "croma.com", 78990),
        _listing("Apple iPhone 13 (128GB) - Midnight", "Flipkart", "flipkart.com", 42999),
        _listing(
            "Apple iPhone 13 (256GB) Blue - Special Series", "Control Z", "controlz.in", 35999
        ),
    ]
    fake = FakeSearch(items)
    monkeypatch.setattr(registry, "product_search_providers", lambda: [fake])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [NoAmazon()])

    for question in ("iphone 17", "should i buy ihpone 17 rigth now or should i wait"):
        r = await client.post("/api/v1/agent", json={"query": question})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["intent"]["product_query"] == "iphone 17", body["intent"]
        names = [p["product"]["name"] for p in body["products"]]
        assert names and all("iPhone 17" in n for n in names), names
        assert "n/a/100" not in body["answer"]
    assert all(q == "iphone 17" for q in fake.queries), fake.queries
    # Buy-timing questions carry the price signal, honest about thin history.
    assert body["intent"]["kind"] == "buy_timing" and body["price_signal"] is not None
