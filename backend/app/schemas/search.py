"""Search schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import DataMeta
from app.schemas.family import ProductFamily
from app.schemas.product import ProductSearchResult


class SearchRequest(BaseModel):
    query: str | None = Field(None, max_length=300)
    url: str | None = Field(None, max_length=2048)
    image_url: str | None = Field(None, max_length=2048)
    image_base64: str | None = None
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, ge=0)
    sort_by: str | None = None  # relevance | price_asc | price_desc | rating
    page: int = Field(1, ge=1, le=20)
    page_size: int = Field(20, ge=1, le=50)


class SearchResponse(BaseModel):
    query: str | None = None
    query_type: str  # text | url | image
    detected_retailer: str | None = None
    reference_product_id: str | None = None
    total_results: int
    page: int
    page_size: int
    results: list[ProductSearchResult] = []
    # When the query names a product line, every variant and retailer of that
    # line in one place. The result cards remain below it.
    family: ProductFamily | None = None
    meta: DataMeta
