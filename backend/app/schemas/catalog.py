"""Category browsing over the curated catalogue."""

from __future__ import annotations

from pydantic import BaseModel


class CatalogModelCard(BaseModel):
    line: str
    label: str
    brand: str
    category: str
    released: str | None = None
    specs: dict
    colors: list[str] = []
    image: str | None = None
    # Live figures from stored offers; withheld (None / 0) without Pro.
    lowest_price: float | None = None
    store_count: int = 0
    offer_count: int = 0
    locked: bool = False


class FacetValue(BaseModel):
    value: str
    count: int


class CatalogFacets(BaseModel):
    brands: list[FacetValue] = []
    ram_gb: list[FacetValue] = []
    storage_gb: list[FacetValue] = []


class CatalogPage(BaseModel):
    category: str
    title: str
    total: int
    models: list[CatalogModelCard] = []
    facets: CatalogFacets
    locked: bool = False
    specs_note: str
