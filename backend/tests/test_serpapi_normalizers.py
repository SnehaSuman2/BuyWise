"""Normalization of SerpApi payloads (fixtures modelled on documented response shapes)."""

from app.providers.base import parse_price
from app.providers.serpapi.amazon_product import normalize_amazon_product
from app.providers.serpapi.amazon_search import normalize_amazon_result
from app.providers.serpapi.google_lens import normalize_visual_match
from app.providers.serpapi.google_product import normalize_seller
from app.providers.serpapi.google_search import normalize_organic_result
from app.providers.serpapi.google_shopping import normalize_shopping_result


def test_parse_price_variants():
    assert parse_price("₹24,990.00") == 24990.0
    assert parse_price("Rs. 1,299") == 1299.0
    assert parse_price(24990) == 24990.0
    assert parse_price({"extracted_value": 999}) == 999.0
    assert parse_price("Free") is None and parse_price(None) is None and parse_price(0) is None


def test_google_shopping_normalization():
    raw = {
        "title": "Sony WH-1000XM5",
        "price": "₹24,990",
        "extracted_price": 24990,
        "old_price": "₹29,990",
        "extracted_old_price": 29990,
        "link": "https://www.google.com/url?q=https://www.amazon.in/dp/B09XS7JWHH",
        "source": "Amazon.in",
        "delivery": "Free delivery",
        "rating": 4.5,
        "reviews": "12,450",
        "product_id": "123",
        "thumbnail": "https://img",
    }
    l = normalize_shopping_result(raw)
    assert l.price == 24990 and l.original_price == 29990 and l.retailer_domain == "amazon.in"
    assert (
        l.shipping_known
        and l.shipping_price == 0
        and l.identifiers["asin"] == "B09XS7JWHH"
        and l.rating_count == 12450
    )
    assert normalize_shopping_result({"price": "₹1"}) is None


def test_amazon_search_normalization_skips_missing_asin_and_handles_prime():
    assert normalize_amazon_result({"title": "x"}, "amazon.in") is None
    l = normalize_amazon_result(
        {
            "title": "Sony",
            "asin": "B0X",
            "price": "₹1,000",
            "prime": True,
            "rating": "4.3",
            "reviews": 10,
        },
        "amazon.in",
    )
    assert (
        l.identifiers["asin"] == "B0X"
        and l.shipping_known
        and l.shipping_price == 0
        and l.url.endswith("/dp/B0X")
    )


def test_amazon_product_normalization():
    data = {
        "product_results": {
            "title": "Sony WH-1000XM5",
            "brand": "Sony",
            "buybox": {
                "price": "₹24,990",
                "seller": {"name": "Appario"},
                "delivery": "FREE delivery Tomorrow",
            },
            "specifications": [{"name": "Item model number", "value": "WH1000XM5/B"}],
            "images": [{"link": "https://img/1"}],
        }
    }
    d = normalize_amazon_product(data, "B09XS7JWHH", "amazon.in")
    assert d.identifiers == {"asin": "B09XS7JWHH", "mpn": "WH1000XM5/B"}
    assert (
        d.offers
        and d.offers[0].seller_name == "Appario"
        and d.offers[0].shipping_known
        and d.offers[0].delivery_days == 1
    )


def test_google_product_seller_normalization():
    l = normalize_seller(
        {
            "name": "Croma",
            "link": "https://www.croma.com/x",
            "base_price": "₹25,990",
            "additional_price": {"shipping": "₹99"},
            "total_price": "₹26,089",
        },
        "pid",
    )
    assert (
        l.price == 25990
        and l.shipping_price == 99
        and l.shipping_known
        and l.retailer_domain == "croma.com"
    )


def test_google_search_and_lens_normalization():
    e = normalize_organic_result(
        {
            "title": "Croma reviews",
            "link": "https://mouthshut.com/croma",
            "snippet": "ok",
            "date": "Jan 5, 2026",
        },
        "croma reviews",
    )
    assert e.query == "croma reviews" and e.published_at.year == 2026
    v = normalize_visual_match(
        {
            "title": "Sony WH-1000XM5",
            "link": "https://www.flipkart.com/x",
            "source": "Flipkart",
            "price": {"value": "₹25,000", "extracted_value": 25000, "currency": "₹"},
        }
    )
    assert v.price == 25000 and v.currency == "INR" and v.retailer_domain == "flipkart.com"


def test_amazon_review_insights_normalization():
    """Amazon aggregates its own review corpus into themed insights with mention counts,
    which gives real pros/cons without needing an AI provider."""
    from app.providers.serpapi.amazon_product import normalize_review_insights

    data = {
        "reviews_information": {
            "summary": {
                "text": "Customers praise the sound quality.",
                "insights": [
                    {
                        "title": "Sound quality",
                        "sentiment": "positive",
                        "mentions": {"total": 291, "positive": 205, "negative": 86},
                        "summary": "Crisp treble.",
                        "examples": [{"snippet": "Great sound", "link": "https://x"}],
                    },
                    {
                        "title": "Value for money",
                        "sentiment": "mixed",
                        "mentions": {"total": 142, "positive": 65, "negative": 77},
                    },
                ],
            }
        }
    }
    insights = normalize_review_insights(
        data, {"reviews": 17217, "rating": 4.4}, "B0X", "amazon.in"
    )
    assert insights.total_reviews == 17217 and insights.average_rating == 4.4
    assert [t.theme for t in insights.themes] == ["Sound quality", "Value for money"]
    assert insights.themes[0].positive_mentions == 205
    assert insights.themes[1].sentiment == "mixed"


def test_implausible_average_rating_is_dropped():
    """A 5.0 average over 17,000 reviews is not a real corpus — better to show nothing."""
    from app.providers.serpapi.amazon_product import normalize_review_insights

    data = {"reviews_information": {"summary": {"text": "Good", "insights": []}}}
    implausible = normalize_review_insights(
        data, {"reviews": 17217, "rating": 5.0}, "B0X", "amazon.in"
    )
    assert implausible.average_rating is None
    # A perfect score on a small corpus is plausible and kept.
    small = normalize_review_insights(data, {"reviews": 7, "rating": 5.0}, "B0X", "amazon.in")
    assert small.average_rating == 5.0
