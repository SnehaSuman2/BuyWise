"""Regression tests for two production bugs found reviewing a live SerpApi search:
generation vs. tier conflict in the matcher, and price-outlier / rental spam."""

import pytest

from app.providers import registry
from app.providers.base import NormalizedListing, ProviderResult
from app.services.product_matcher import Candidate, MatchType, match_products
from app.services.product_normalizer import extract_attributes
from app.services.search_service import filter_implausible_price_outliers


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


def test_implausible_price_outlier_is_dropped_without_ever_grouping():
    """The real bug: a bare-title spam listing scores just under the 0.75 grouping
    threshold against fuller listings of the same phone, so it never shares a group
    with them and a post-grouping check would never see it. This one is dropped by
    line-token clustering before grouping happens at all."""
    listings = [
        _listing("Apple iPhone 17 Pro 512GB Silver MG8K4HN/A", "Amazon.in", 149989),
        _listing("Apple iPhone 17 Pro 1TB Cosmic Orange", "Croma", 174900),
        _listing("Apple iPhone 17 Pro 256GB Orange", "Flipkart", 124999),
        _listing("Apple iPhone 17 Pro", "Meesho", 148),  # spam / mismatched listing
    ]
    kept, dropped = filter_implausible_price_outliers(listings)
    assert dropped == 1
    assert 148 not in {listing.price for listing in kept}
    assert {149989, 174900, 124999} <= {listing.price for listing in kept}


def test_implausible_price_filter_never_compares_across_different_tiers():
    """iPhone 17 Pro and iPhone 17 Pro Max are different products with legitimately
    different prices; the low end of one line must never sink the other."""
    listings = [
        _listing("Apple iPhone 17 Pro 256GB", "Amazon.in", 124999),
        _listing("Apple iPhone 17 Pro 512GB", "Croma", 149989),
        _listing("Apple iPhone 17 Pro 1TB", "Flipkart", 174900),
        _listing("Apple iPhone 17 Pro Max 512GB", "Amazon.in", 169900),
        _listing("Apple iPhone 17 Pro Max 1TB", "Croma", 199900),
        _listing("Apple iPhone 17 Pro Max", "Meesho", 273),  # spam
    ]
    kept, dropped = filter_implausible_price_outliers(listings)
    assert dropped == 1
    assert 273 not in {listing.price for listing in kept}
    assert 124999 in {listing.price for listing in kept}  # the cheapest real Pro survives
    assert 169900 in {listing.price for listing in kept}  # the cheapest real Pro Max survives


def test_implausible_price_filter_requires_at_least_three_priced_listings_in_the_family():
    """A lone cheap listing with nothing to compare against is left alone — this
    is a self-referential check, not an absolute price floor."""
    listings = [
        _listing("Apple iPhone 17 Pro 256GB", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro", "Meesho", 148),
    ]
    kept, dropped = filter_implausible_price_outliers(listings)
    assert dropped == 0 and len(kept) == 2


def test_implausible_price_filter_tolerates_real_discounts():
    """A genuine sale price (well above the 20% floor) must survive."""
    listings = [
        _listing("Apple iPhone 17 Pro 256GB", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro 512GB", "Croma", 129900),
        _listing("Apple iPhone 17 Pro 1TB", "Flipkart", 99900),  # ~26% off, real sale
    ]
    kept, dropped = filter_implausible_price_outliers(listings)
    assert dropped == 0 and len(kept) == 3


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


def test_housing_spare_parts_are_accessories():
    assert extract_attributes("Full Body Housing for Apple iPhone 17 Pro - Black").is_accessory
    assert not extract_attributes("Apple iPhone 17 Pro 256GB Black").is_accessory


def test_cheap_spam_cannot_become_the_reference_price():
    """Seen live: three listings for one line at ₹273, ₹6,607 and ₹2,12,923. A median
    reference is ₹6,607 and the ₹6,607 case survives. The upper-quartile reference
    drops both."""
    listings = [
        _listing("Apple iPhone 17 Pro Max, US Version, 256GB", "Amazon.in", 212923),
        _listing("Apple iPhone 17 Pro Max", "Meesho", 273),
        _listing("iPhone 17 Pro Max AirX Flux Gray", "rhinoshield.io", 6607.79),
    ]
    kept, dropped = filter_implausible_price_outliers(listings)
    assert dropped == 2 and [listing.price for listing in kept] == [212923]


@pytest.mark.asyncio
async def test_stale_spam_offer_is_retired_once_real_offers_arrive(client, monkeypatch):
    """A spam offer recorded before the filters existed keeps setting the product's
    lowest price for ever unless something retires it. Persisting the product again
    with enough genuine offers must do exactly that, and the product page must agree."""
    monkeypatch.setattr(registry, "retailer_search_providers", lambda: [FakeRetailerSearch()])

    # Search 1: too few listings for the family filter, so the spam is persisted.
    first = [
        _listing("Apple iPhone 17 Pro 256GB Black", "Amazon.in", 134900),
        _listing("Apple iPhone 17 Pro 256GB Black", "Meesho", 148),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(first)])
    r1 = await client.post("/api/v1/search", json={"query": "iphone 17 pro 256gb"})
    assert r1.status_code == 200, r1.text
    product = next(x for x in r1.json()["results"] if "Pro 256GB" in x["name"])
    assert product["lowest_price"] == 148  # the bug, before enough evidence exists

    # Search 2: genuine offers from other retailers join the same product.
    second = [
        _listing("Apple iPhone 17 Pro 256GB Black", "Croma", 129900),
        _listing("Apple iPhone 17 Pro 256GB Black", "Flipkart", 132900),
        _listing("Apple iPhone 17 Pro 256GB Black", "Vijay Sales", 131900),
    ]
    monkeypatch.setattr(registry, "product_search_providers", lambda: [FakeSearch(second)])
    r2 = await client.post("/api/v1/search", json={"query": "iphone 17 pro 256gb"})
    healed = next(x for x in r2.json()["results"] if x["id"] == product["id"])
    assert healed["lowest_price"] == 129900, healed
    assert "Meesho" not in healed["retailers"]

    offers = await client.get(f"/api/v1/products/{product['id']}/offers")
    assert offers.status_code == 200
    prices = sorted(o["price"]["estimated_final_price"] for o in offers.json()["offers"])
    assert 148 not in prices and prices[0] == 129900


def test_result_cards_with_only_spam_prices_are_hidden():
    import uuid

    from app.schemas.product import ProductSearchResult

    def card(name, price):
        return ProductSearchResult(
            id=uuid.uuid4(),
            name=name,
            brand="Apple",
            category=None,
            image=None,
            lowest_price=price,
            highest_price=price,
            offer_count=1,
            retailers=["x"],
            average_rating=None,
            match=None,
            is_demo=False,
        )

    from app.services.search_service import hide_implausible_results

    results = [
        card("Apple iPhone 17 Pro Max, US Version, 256GB", 212923),
        card("Apple iPhone 17 Pro Max 1TB", 199900),
        card("Apple iPhone 17 Pro Max", 273),
        card("iPhone 17 Pro Max AirX Flux Gray", 6607.79),
        card("Apple iPhone 17 256GB White", 68999),  # different line, untouched
    ]
    kept, hidden = hide_implausible_results(results)
    assert hidden == 2
    assert {r.lowest_price for r in kept} == {212923, 199900, 68999}
