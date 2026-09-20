"""Product matching: same product vs different variant vs similar."""

from app.services.product_matcher import Candidate, MatchType, match_products, quick_match
from app.services.product_normalizer import extract_attributes


def test_storage_variant_is_not_exact():
    r = quick_match("Apple iPhone 17 256GB Black", "Apple iPhone 17 512GB Black")
    assert r.match_type == MatchType.DIFFERENT_VARIANT
    assert any("storage" in reason for reason in r.reasons)


def test_same_variant_is_exact():
    r = quick_match("Apple iPhone 17 256GB Black", "iPhone 17 (256 GB) - Black")
    assert r.match_type == MatchType.EXACT
    assert r.confidence >= 0.75


def test_gtin_match_wins():
    r = quick_match(
        "Some odd title",
        "Completely different title",
        {"gtin": "4548736132610"},
        {"gtin": "4548736132610"},
    )
    assert r.match_type == MatchType.EXACT and r.confidence >= 0.98


def test_gtin_mismatch_same_family_is_variant():
    r = quick_match("Sony WH-1000XM5 Black", "Sony WH-1000XM5 Silver", {"gtin": "1"}, {"gtin": "2"})
    assert r.match_type == MatchType.DIFFERENT_VARIANT


def test_colour_variant():
    r = quick_match(
        "Sony WH-1000XM5 Wireless Headphones (Black)",
        "Sony WH-1000XM5 Wireless Headphones (Silver)",
    )
    assert r.match_type == MatchType.DIFFERENT_VARIANT


def test_model_generation_differs():
    r = quick_match("Sony WH-1000XM5 Headphones", "Sony WH-1000XM4 Headphones")
    assert r.match_type in (MatchType.SIMILAR, MatchType.UNKNOWN)
    assert r.match_type != MatchType.EXACT


def test_lineup_modifier_differs():
    r = quick_match("Samsung Galaxy S24 Ultra 256GB", "Samsung Galaxy S24 256GB")
    assert r.match_type == MatchType.SIMILAR


def test_accessory_not_product():
    r = quick_match(
        "Apple iPhone 15 Pro Max 256GB", "Spigen Ultra Hybrid Case for iPhone 15 Pro Max"
    )
    assert r.match_type == MatchType.SIMILAR


def test_brand_mismatch():
    r = quick_match("Sony WH-1000XM5", "Bose QuietComfort 45")
    assert r.match_type != MatchType.EXACT


def test_ram_storage_pair_extraction():
    a = extract_attributes("Samsung Galaxy S24 Ultra 5G (Titanium Gray, 12GB, 256GB Storage)")
    assert (
        a.ram == "12GB"
        and a.storage == "256GB"
        and a.color == "titanium gray"
        and a.brand == "samsung"
    )


def test_product_line_brand_inference():
    assert extract_attributes("iPhone 15 Pro Max 256GB").brand == "apple"
    assert extract_attributes("Galaxy Watch6 Classic 47mm").brand == "samsung"


def test_slug_split_model_code_matches():
    r = match_products(
        Candidate("sony wh 1000xm5 bluetooth headset"),
        Candidate("Sony WH-1000XM5 Wireless Noise Cancelling Headphones (Black)"),
    )
    assert r.match_type == MatchType.EXACT
    r2 = match_products(
        Candidate("sony wh 1000xm5 bluetooth headset"),
        Candidate("Sony WF-1000XM5 True Wireless Earbuds"),
    )
    assert r2.match_type != MatchType.EXACT


def test_missing_variant_info_lowers_confidence():
    full = quick_match(
        "Apple iPhone 15 Pro 256GB Blue Titanium", "Apple iPhone 15 Pro 256GB Blue Titanium"
    )
    partial = quick_match("Apple iPhone 15 Pro 256GB Blue Titanium", "Apple iPhone 15 Pro")
    assert full.match_type == MatchType.EXACT and partial.match_type == MatchType.EXACT
    assert partial.confidence < full.confidence
    assert partial.label == "Possible match"


def test_accessory_listings_never_match_the_product_itself():
    """Regression: a ₹1,200 decal was being grouped into a ₹25,000 headphone listing
    in production, becoming the "cheapest" pick. Accessory nouns (including plurals)
    must be enough on their own to keep a listing out of the product's own group."""
    product = "Sony WH-1000XM5 Wireless Noise Cancelling Headphones"
    for accessory in (
        "XtremeSkins Sony WH-1000XM5 Skins & Wraps UK",
        "Sony WH-1000XM5 Replacement Ear Pads",
        "Hard Carrying Case for Sony WH-1000XM5",
        "Sony WH-1000XM5 Headphone Stand",
    ):
        result = quick_match(product, accessory)
        assert result.match_type != MatchType.EXACT, f"{accessory!r} matched as the product"


def test_real_product_listings_still_match_despite_accessory_fix():
    """The accessory fix must not make genuine listings stop matching."""
    product = "Sony WH-1000XM5 Wireless Noise Cancelling Headphones"
    for genuine in (
        "Sony WH-1000XM5 Industry Leading Noise-Cancelling Headphones",
        "Sony WH-1000XM5 Wireless Noise Canceling Headphones",
    ):
        assert quick_match(product, genuine).match_type == MatchType.EXACT, genuine


def test_accessory_to_accessory_still_compares_normally():
    """Someone searching for a case should still get case-to-case comparisons."""
    result = quick_match(
        "Spigen Ultra Hybrid Case for iPhone 15 Pro Max",
        "Spigen Ultra Hybrid Case for iPhone 15 Pro Max",
    )
    assert result.match_type == MatchType.EXACT


def test_accessories_hidden_unless_the_shopper_asks_for_them():
    """A ₹999 skin beside ₹22,000 headphones reads as a suspiciously cheap version of
    the product. Hide accessories unless the query names one."""
    from app.providers.base import NormalizedListing
    from app.services.search_service import filter_accessories

    listings = [
        NormalizedListing(
            title="Sony WH-1000XM5 Wireless Noise Cancelling Headphones", price=21990.0
        ),
        NormalizedListing(title="Sony WH-1000XM5 Wireless Headphone Skins & Wraps", price=999.0),
        NormalizedListing(title="WC SweatZ XM5 Protective Covers for Sony", price=999.0),
    ]

    kept, dropped = filter_accessories(listings, "Sony WH-1000XM5")
    assert dropped == 2
    assert [listing.title for listing in kept] == [
        "Sony WH-1000XM5 Wireless Noise Cancelling Headphones"
    ]

    # Asking for the accessory brings them back.
    kept, dropped = filter_accessories(listings, "Sony WH-1000XM5 skins")
    assert dropped == 0 and len(kept) == 3

    kept, dropped = filter_accessories(listings, "iPhone 15 case")
    assert dropped == 0 and len(kept) == 3
