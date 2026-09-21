"""Regression tests for two production bugs found reviewing a live SerpApi search:
generation vs. tier conflict in the matcher, and price-outlier / rental spam."""

import pytest

from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.services.product_matcher import Candidate, MatchType, match_products
from app.services.product_normalizer import extract_attributes
from app.services.search_service import drop_implausible_prices, group_listings


def test_generation_and_tier_both_differing_is_not_a_sibling_match():
    """iPhone 15 Pro Max is not a 'different tier' of iPhone 17 — it's a different
    generation entirely. Before this fix the tier check short-circuited before the
    generation was ever compared."""
    r = match_products(Candidate("iphone 17"), Candidate("Apple iPhone 15 Pro Max"))
    assert r.match_type in (MatchType.UNKNOWN, MatchType.SIMILAR)
    assert any(x.startswith("Generation differs") for x in r.reasons)
    assert r.confidence <= 0.35


def test_same_generation_different_tier_is_still_a_sibling():
    """The fix must not affect true siblings: same generation, different tier."""
    for candidate in ("Apple iPhone 17 Pro", "Apple iPhone 17 Pro Max"):
        r = match_products(Candidate("iphone 17"), Candidate(candidate))
        assert r.match_type == MatchType.SIMILAR and r.confidence == 0.7
        assert not any(x.startswith("Generation differs") for x in r.reasons)

    r = match_products(Candidate("Samsung Galaxy S24"), Candidate("Samsung Galaxy S24 Ultra"))
    assert r.match_type == MatchType.SIMILAR and r.confidence == 0.7


def test_spare_parts_are_accessories_even_without_the_word_accessory():
    for title in (
        "Apple iPhone 17 5G Full Housing Body Panel White | ORIGINAL",
        "iPhone 15 Pro Max Back Glass Replacement",
        "Samsung Galaxy S24 Ultra Digitizer Screen",
    ):
        assert extract_attributes(title).is_accessory, title


def test_rental_listings_are_flagged():
    assert extract_attributes("Apple iPhone 17 Pro Max on Rent | 48MP ProRAW | 5K").is_rental
    assert extract_attributes("iPhone 15 for rent in Bangalore").is_rental
    assert not extract_attributes("Apple iPhone 17 Pro Max 256GB").is_rental


def _listing(title, retailer, price):
    return NormalizedListing(
        title=title,
        url=f"https://www.example.in/p/{abs(hash(title + retailer)) % 10**6}",
        price=price,
        retailer_name=retailer,
        retailer_domain="example.in",
        source_provider="test",
        source_engine="fake",
    )


def test_implausible_price_outlier_is_dropped_from_its_own_group():
    listings = [
        _listing("Apple iPhone 17 Pro", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro", "Croma", 129900),
        _listing("Apple iPhone 17 Pro", "Flipkart", 132900),
        _listing("Apple iPhone 17 Pro", "Meesho", 148),  # spam / mismatched listing
    ]
    groups = group_listings(listings)
    assert len(groups) == 1 and len(groups[0].listings) == 4
    dropped = drop_implausible_prices(groups)
    assert dropped == 1
    prices = sorted(listing.price for listing, _ in groups[0].listings)
    assert prices == [129900, 132900, 134900]


def test_implausible_price_filter_requires_at_least_three_priced_listings():
    """A lone cheap listing with nothing to compare against is left alone — this
    is a self-referential check, not an absolute price floor."""
    listings = [
        _listing("Apple iPhone 17 Pro", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro", "Meesho", 148),
    ]
    groups = group_listings(listings)
    assert drop_implausible_prices(groups) == 0
    assert len(groups[0].listings) == 2


def test_implausible_price_filter_tolerates_real_discounts():
    """A genuine sale price (well above the 20% floor) must survive."""
    listings = [
        _listing("Apple iPhone 17 Pro", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro", "Croma", 129900),
        _listing("Apple iPhone 17 Pro", "Flipkart", 99900),  # ~26% off, real sale
    ]
    groups = group_listings(listings)
    assert drop_implausible_prices(groups) == 0
    assert len(groups[0].listings) == 3


class FakeSearch:
    name = "test"
    engine = "fake_shopping"
    enabled = True

    def __init__(self, items):
        self.items = items

    async def search_products(self, query, *, max_results=20, min_price=None, max_price=None):
        return ProviderResult(items=list(self.items), provider=self.name, engine=self.engine)


class FakeRetailerSearch:
    name = "test"
    engine = "fake_amazon"
    enabled = True
    retailer_slug = "amazon-india"

    async def search_retailer(self, query, *, max_results=10):
        return ProviderResult(items=[], provider=self.name, engine=self.engine)


@pytest.mark.asyncio
async def test_search_end_to_end_hides_wrong_generation_spam_and_rentals(client, monkeypatch):
    items = [
        _listing("Apple iPhone 17 (256 GB) - Black", "Amazon.in", 79900),
        _listing("Apple iPhone 17 256GB Black", "Flipkart", 79490),
        _listing("Apple iPhone 17 256GB", "Croma", 78990),
        _listing("Apple iPhone 15 Pro Max (128 GB)", "Croma", 56900),
        _listing(
            "Apple iPhone 17 5G Full Housing Body Panel White | ORIGINAL", "Cellspare.com", 10539
        ),
        _listing("Apple iPhone 17 Pro Max on Rent | 48MP ProRAW", "RentPhones", 573),
        _listing("Apple iPhone 17 Pro", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro", "Croma", 129900),
        _listing("Apple iPhone 17 Pro", "Flipkart", 132900),
        _listing("Apple iPhone 17 Pro", "Meesho", 148),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(items)])
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])

    r = await client.post("/api/v1/search", json={"query": "iphone 17", "page_size": 24})
    assert r.status_code == 200, r.text
    body = r.json()
    names = [x["name"] for x in body["results"]]
    prices = {x["name"]: x["lowest_price"] for x in body["results"]}

    assert not any("iPhone 15" in n for n in names), names
    assert not any("Housing" in n or "Body Panel" in n for n in names), names
    assert not any("Rent" in n for n in names), names
    pro_price = next(v for k, v in prices.items() if k == "Apple iPhone 17 Pro")
    assert pro_price >= 129900, prices  # the ₹148 Meesho spam must not set the price

    warnings = " ".join(body["meta"]["warnings"])
    assert "different model" in warnings
    assert "rental" in warnings
    assert "priced far below" in warnings
