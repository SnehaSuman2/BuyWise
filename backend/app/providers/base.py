"""Provider interfaces and normalized data transfer models.

Every external integration (SerpApi engines, demo providers, Trustpilot, ...)
returns these normalized models. Nothing downstream ever sees raw provider JSON.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- normalized models
class NormalizedListing(BaseModel):
    """A product listing seen at a retailer (search result or product page offer)."""

    title: str
    url: str | None = None
    image_url: str | None = None
    price: float | None = None
    original_price: float | None = None
    currency: str = "INR"
    retailer_name: str | None = None
    retailer_domain: str | None = None
    seller_name: str | None = None
    shipping_price: float | None = None
    shipping_known: bool = False
    coupon_code: str | None = None
    coupon_amount: float | None = None
    delivery_text: str | None = None
    delivery_days: int | None = None
    availability: str = "unknown"  # in_stock | out_of_stock | limited | unknown
    condition: str = "new"
    rating: float | None = None
    rating_count: int | None = None
    brand: str | None = None
    category: str | None = None
    snippet: str | None = None
    identifiers: dict[str, str] = Field(
        default_factory=dict
    )  # asin, gtin, mpn, sku, google_product_id
    source_provider: str = "unknown"
    source_engine: str | None = None
    observed_at: datetime = Field(default_factory=utcnow)
    is_demo: bool = False


class ReviewTheme(BaseModel):
    """One aspect customers repeatedly mention, with how the mentions split."""

    theme: str
    sentiment: str  # positive | negative | mixed
    total_mentions: int = 0
    positive_mentions: int = 0
    negative_mentions: int = 0
    summary: str | None = None
    examples: list[str] = Field(default_factory=list)


class NormalizedReviewInsights(BaseModel):
    """Aggregated review themes for a product, as published by the retailer.

    Marketplaces already aggregate their own review corpus into themed insights with
    real mention counts. Using those beats having an LLM summarise a handful of scraped
    reviews: the counts are drawn from the full corpus and each theme links to sources.
    """

    summary: str | None = None
    total_reviews: int | None = None
    average_rating: float | None = None
    themes: list[ReviewTheme] = Field(default_factory=list)
    source: str = "unknown"
    source_url: str | None = None


class NormalizedProductDetails(BaseModel):
    """Details of one product page (e.g. Amazon Product API)."""

    title: str
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    description: str | None = None
    images: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    identifiers: dict[str, str] = Field(default_factory=dict)
    variants: list[dict] = Field(default_factory=list)
    offers: list[NormalizedListing] = Field(default_factory=list)
    review_insights: NormalizedReviewInsights | None = None
    source_provider: str = "unknown"
    source_engine: str | None = None
    source_url: str | None = None
    is_demo: bool = False


class EvidenceItem(BaseModel):
    """A single piece of trust evidence, before analysis."""

    source: (
        str  # google_search | retailer_policy | trustpilot | community | buywise_verified | demo
    )
    source_type: (
        str  # search_result | policy | review_platform | community_report | verified_purchase
    )
    url: str | None = None
    title: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    query: str | None = None  # the search query that produced it (search_result only)
    # Optional pre-analysed fields (policy/Trustpilot providers fill these directly)
    topic: str | None = None
    sentiment: float | None = None
    severity: float | None = None
    confidence: float | None = None
    extracted_claim: str | None = None
    is_demo: bool = False


class ProviderResult(BaseModel, Generic[T]):
    """Wraps provider output so callers can degrade gracefully."""

    items: list[T] = Field(default_factory=list)
    provider: str
    engine: str | None = None
    ok: bool = True
    error: str | None = None
    cached: bool = False
    is_demo: bool = False
    latency_ms: int | None = None

    @classmethod
    def failure(cls, provider: str, engine: str | None, error: str) -> "ProviderResult[T]":
        return cls(items=[], provider=provider, engine=engine, ok=False, error=error)


# ---------------------------------------------------------------- interfaces
class BaseProvider(ABC):  # noqa: B024 - shared base; subclasses declare abstract methods
    name: str = "base"
    engine: str | None = None
    is_demo: bool = False

    @property
    def enabled(self) -> bool:
        return True


class ProductSearchProvider(BaseProvider):
    """Search for product listings across retailers (Google Shopping, Bing Shopping, demo)."""

    @abstractmethod
    async def search_products(
        self,
        query: str,
        *,
        max_results: int = 20,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> ProviderResult[NormalizedListing]: ...


class RetailerSearchProvider(BaseProvider):
    """Search within one retailer (Amazon Search)."""

    retailer_slug: str = ""

    @abstractmethod
    async def search_retailer(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[NormalizedListing]: ...


class ProductDetailsProvider(BaseProvider):
    """Fetch a single product page with identifiers and offers (Amazon Product, Google Product)."""

    @abstractmethod
    async def get_product_details(
        self, identifier: str
    ) -> ProviderResult[NormalizedProductDetails]: ...


class ImageSearchProvider(BaseProvider):
    """Find product listings from an image (Google Lens, Reverse Image)."""

    @abstractmethod
    async def search_by_image(self, image_url: str) -> ProviderResult[NormalizedListing]: ...


class WebSearchProvider(BaseProvider):
    """Generic web search (Google Search) — used for URL resolution and trust evidence."""

    @abstractmethod
    async def search_web(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[EvidenceItem]: ...


class TrustEvidenceProvider(BaseProvider):
    """Collects public evidence about a retailer/seller (Google Search, Trustpilot, demo)."""

    @abstractmethod
    async def collect_evidence(
        self, retailer_name: str, domain: str | None = None
    ) -> ProviderResult[EvidenceItem]: ...


ReviewEvidenceProvider = TrustEvidenceProvider  # alias used in docs


# ---------------------------------------------------------------- helpers
def parse_price(value) -> float | None:
    """Parse '₹24,990.00', '24990', 24990, {'value': 24990} into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, dict):
        for k in ("extracted_value", "value", "raw"):
            if k in value:
                return parse_price(value[k])
        return None
    if isinstance(value, str):
        cleaned = (
            value.replace(",", "").replace("₹", "").replace("Rs.", "").replace("INR", "").strip()
        )
        num = ""
        seen_digit = False
        for ch in cleaned:
            if ch.isdigit() or (ch == "." and seen_digit):
                num += ch
                seen_digit = True
            elif seen_digit:
                break
        try:
            parsed = float(num)
            return parsed if parsed > 0 else None
        except ValueError:
            return None
    return None


def parse_int(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(ch for ch in value.replace(",", "") if ch.isdigit())
        return int(digits) if digits else None
    return None
