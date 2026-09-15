"""True price engine.

  Listed price
  + Shipping (only if known)
  - Coupon (only if actually known)
  = Estimated final price

`original_price` (MRP/strike-through) is informational: the listed price already
reflects it. Unknown components stay unknown and produce a checkout warning.
Nothing is ever invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.providers.base import NormalizedListing


@dataclass
class TruePrice:
    listed_price: float
    original_price: float | None
    discount_amount: float | None
    shipping_price: float | None
    shipping_known: bool
    coupon_code: str | None
    coupon_amount: float | None
    estimated_final_price: float
    final_price_known: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "listed_price": self.listed_price,
            "original_price": self.original_price,
            "discount_amount": self.discount_amount,
            "discount_percent": round(self.discount_amount / self.original_price * 100, 1)
            if self.discount_amount and self.original_price
            else None,
            "shipping_price": self.shipping_price,
            "shipping_known": self.shipping_known,
            "coupon_code": self.coupon_code,
            "coupon_amount": self.coupon_amount,
            "estimated_final_price": self.estimated_final_price,
            "final_price_known": self.final_price_known,
            "notes": self.notes,
        }


def compute_true_price(
    listed_price: float,
    *,
    original_price: float | None = None,
    shipping_price: float | None = None,
    shipping_known: bool = False,
    coupon_code: str | None = None,
    coupon_amount: float | None = None,
) -> TruePrice:
    if listed_price is None or listed_price <= 0:
        raise ValueError("listed_price must be positive")
    notes: list[str] = []
    discount = None
    if original_price and original_price > listed_price:
        discount = round(original_price - listed_price, 2)
    elif original_price and original_price <= listed_price:
        original_price = None  # not a real strike-through

    shipping = shipping_price if shipping_known else None
    if shipping_known and shipping is None:
        shipping = 0.0
    if not shipping_known:
        notes.append("Shipping not confirmed — final price may vary at checkout.")

    coupon = None
    if coupon_amount and coupon_amount > 0:
        coupon = round(min(coupon_amount, listed_price), 2)
        notes.append(
            f"Coupon {coupon_code or ''} applied only if valid at checkout.".replace("  ", " ")
        )
    elif coupon_code and not coupon_amount:
        notes.append(f"Coupon {coupon_code} available; discount amount unknown.")

    final = round(listed_price + (shipping or 0.0) - (coupon or 0.0), 2)
    final_known = shipping_known and coupon is None
    return TruePrice(
        listed_price=round(listed_price, 2),
        original_price=round(original_price, 2) if original_price else None,
        discount_amount=discount,
        shipping_price=shipping,
        shipping_known=shipping_known,
        coupon_code=coupon_code,
        coupon_amount=coupon,
        estimated_final_price=final,
        final_price_known=final_known,
        notes=notes,
    )


def true_price_from_listing(listing: NormalizedListing) -> TruePrice | None:
    if not listing.price:
        return None
    return compute_true_price(
        listing.price,
        original_price=listing.original_price,
        shipping_price=listing.shipping_price,
        shipping_known=listing.shipping_known,
        coupon_code=listing.coupon_code,
        coupon_amount=listing.coupon_amount,
    )
