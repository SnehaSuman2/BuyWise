"""Market filtering: BuyWise serves India, so foreign storefronts must not appear.

The domains here are the real merchants Google Shopping returned for a live
"Sony WH-1000XM5" search in production.
"""

import pytest

from app.core.config import get_settings
from app.providers.base import NormalizedListing
from app.services.market_filter import (
    FOREIGN,
    INDIA,
    UNKNOWN,
    classify_market,
    filter_to_market,
)


@pytest.mark.parametrize(
    "domain,expected",
    [
        # curated registry
        ("amazon.in", INDIA),
        ("flipkart.com", INDIA),
        ("croma.com", INDIA),
        ("myntra.com", INDIA),
        ("reliancedigital.in", INDIA),
        ("tatacliq.com", INDIA),
        # Indian ccTLD
        ("headphonezone.in", INDIA),
        ("somestore.co.in", INDIA),
        # subdomains of curated retailers
        ("dl.flipkart.com", INDIA),
        # known-Indian generic TLD
        ("snapdeal.com", INDIA),
        ("lenskart.com", INDIA),
        # clearly foreign
        ("xtremeskins.co.uk", FOREIGN),
        ("shop.example.jp", FOREIGN),
        ("empire.co.tz", FOREIGN),
        ("store.com.tr", FOREIGN),
        ("papita.co", FOREIGN),
        ("mygsm.me", FOREIGN),
        # unrecognised generic TLD
        ("wafuu.com", UNKNOWN),
        ("newasnew.com", UNKNOWN),
    ],
)
def test_domain_classification(domain, expected):
    assert classify_market(domain) == expected


def test_name_fallback_when_domain_missing():
    assert classify_market(None, "Croma") == INDIA
    assert classify_market(None, "Some Unknown Shop") == UNKNOWN


def _listing(domain, name, price=1000.0):
    return NormalizedListing(
        title="Sony WH-1000XM5", retailer_domain=domain, retailer_name=name, price=price
    )


def test_strict_filter_keeps_only_indian_merchants(monkeypatch):
    monkeypatch.setattr(get_settings(), "STRICT_MARKET_FILTER", True)
    listings = [
        _listing("amazon.in", "Amazon.in"),
        _listing("flipkart.com", "Flipkart"),
        _listing("xtremeskins.co.uk", "XtremeSkins"),
        _listing("wafuu.com", "wafuu.com"),
        _listing("empire.co.tz", "Empire Online Shopping"),
    ]
    kept, excluded, names = filter_to_market(listings)
    assert [listing.retailer_name for listing in kept] == ["Amazon.in", "Flipkart"]
    assert excluded == 3
    assert "XtremeSkins" in names and "wafuu.com" in names


def test_non_strict_keeps_unknown_merchants(monkeypatch):
    monkeypatch.setattr(get_settings(), "STRICT_MARKET_FILTER", False)
    listings = [
        _listing("amazon.in", "Amazon.in"),
        _listing("wafuu.com", "wafuu.com"),          # unknown -> kept when lenient
        _listing("empire.co.tz", "Empire Online"),   # foreign -> still excluded
    ]
    kept, excluded, _ = filter_to_market(listings)
    assert [listing.retailer_name for listing in kept] == ["Amazon.in", "wafuu.com"]
    assert excluded == 1


def test_filter_can_be_disabled_entirely(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "MARKET_FILTER_ENABLED", False)
    listings = [_listing("empire.co.tz", "Empire Online")]
    kept, excluded, _ = filter_to_market(listings)
    assert len(kept) == 1 and excluded == 0


def test_falls_back_to_listing_url_when_domain_absent():
    listing = NormalizedListing(
        title="Sony WH-1000XM5",
        url="https://www.amazon.in/dp/B09XS7JWHH",
        retailer_name=None,
        price=25000.0,
    )
    kept, excluded, _ = filter_to_market([listing])
    assert len(kept) == 1 and excluded == 0


def test_google_shopping_name_only_listings_classify_correctly():
    """Google Shopping returns no merchant URL — only a display name and a google.com
    product_link. The merchant name must drive the decision, not the aggregator domain."""
    from app.services.market_filter import classify_market

    assert classify_market("google.com", "Amazon.in") == INDIA
    assert classify_market("google.com", "TATA CLiQ LUXURY") == INDIA
    assert classify_market("google.com", "TechCommerce.in") == INDIA
    assert classify_market("google.com", "papita.co") == FOREIGN
    assert classify_market("google.com", "Some Random Store") == UNKNOWN


def test_foreign_text_signals():
    from app.services.market_filter import has_foreign_signal

    assert has_foreign_signal("SONY Headphones WH-1000XM5 | Headphones in Dar Tanzania")
    assert has_foreign_signal("sony WH-1000XM5 シルバー")
    # Hindi is an Indian-market listing, not a foreign one.
    assert not has_foreign_signal("Sony WH-1000XM5 बेस्ट एक्टिव नॉइज़ कैंसलिंग")
    assert not has_foreign_signal("Sony WH-1000XM5 Wireless Headphones")


def test_foreign_signal_overrides_an_indian_looking_merchant():
    """A Tanzanian storefront listing under a generic name must still be dropped."""
    listing = NormalizedListing(
        title="SONY Headphones WH-1000XM5 | Headphones in Dar Tanzania",
        retailer_name="Empire Online Shopping",
        price=38994.0,
    )
    kept, excluded, _ = filter_to_market([listing])
    assert kept == [] and excluded == 1
