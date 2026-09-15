import pytest

from app.providers.base import NormalizedListing
from app.services.price_engine import compute_true_price, true_price_from_listing


def test_true_price_with_known_shipping_and_coupon():
    tp = compute_true_price(
        7499,
        original_price=7999,
        shipping_price=0,
        shipping_known=True,
        coupon_code="SAVE500",
        coupon_amount=500,
    )
    assert tp.discount_amount == 500
    assert tp.estimated_final_price == 6999
    assert tp.final_price_known is False  # coupons are conditional
    assert any("Coupon" in n for n in tp.notes)


def test_unknown_shipping_is_flagged_not_assumed():
    tp = compute_true_price(1000, shipping_known=False)
    assert tp.shipping_price is None
    assert tp.estimated_final_price == 1000
    assert tp.final_price_known is False
    assert any("checkout" in n.lower() for n in tp.notes)


def test_known_shipping_final_price_known():
    tp = compute_true_price(1000, shipping_price=49, shipping_known=True)
    assert tp.estimated_final_price == 1049 and tp.final_price_known is True and tp.notes == []


def test_bogus_original_price_ignored():
    tp = compute_true_price(1000, original_price=900)
    assert tp.original_price is None and tp.discount_amount is None


def test_coupon_cannot_exceed_price():
    tp = compute_true_price(100, coupon_amount=500, coupon_code="X")
    assert tp.estimated_final_price == 0


def test_invalid_price():
    with pytest.raises(ValueError):
        compute_true_price(0)


def test_listing_without_price():
    assert true_price_from_listing(NormalizedListing(title="x")) is None
