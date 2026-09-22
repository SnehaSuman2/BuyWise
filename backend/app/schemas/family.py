"""A product family: one line ("iPhone 17") across its storage and colour
variants, with every retailer's offer in one list."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class FamilyOffer(BaseModel):
    offer_id: UUID
    product_id: UUID
    retailer_id: UUID
    retailer_name: str
    seller_name: str | None = None
    storage: str | None = None
    color: str | None = None
    condition: str = "new"
    price: float
    listed_price: float
    shipping_known: bool = False
    final_price_known: bool = False
    availability: str = "unknown"
    delivery_text: str | None = None
    delivery_days: int | None = None
    trust_score: int | None = None
    go_url: str
    observed_at: datetime
    is_demo: bool = False
    # Priced far above the other stores for the same variant. Judged only
    # against those stores, never against a price list.
    above_market: bool = False


class FamilyVariant(BaseModel):
    storage: str | None = None
    label: str
    colors: list[str] = []
    product_ids: list[UUID] = []
    offer_count: int = 0
    retailer_count: int = 0
    lowest_price: float | None = None
    highest_price: float | None = None
    typical_price: float | None = None
    offers: list[FamilyOffer] = []


class ProductFamily(BaseModel):
    line: str
    label: str
    brand: str | None = None
    image: str | None = None
    variants: list[FamilyVariant] = []
    selected_storage: str | None = None
    total_offers: int = 0
    total_retailers: int = 0
    product_count: int = 0
    is_demo: bool = False
    # Prices and retailers are part of Pro. When withheld the counts stay so the
    # page can say what Pro would show.
    locked: bool = False
    hint: str | None = None
