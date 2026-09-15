"""Provider registry: picks live or demo implementations from configuration.

Live providers are chosen automatically once credentials exist. Demo providers are
the fallback and always label their output is_demo=True.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import (
    ImageSearchProvider,
    ProductDetailsProvider,
    ProductSearchProvider,
    RetailerSearchProvider,
    TrustEvidenceProvider,
    WebSearchProvider,
)
from app.providers.demo.evidence import DemoTrustEvidenceProvider
from app.providers.demo.search import (
    DemoImageSearchProvider,
    DemoProductDetailsProvider,
    DemoProductSearchProvider,
    DemoRetailerSearchProvider,
)
from app.providers.serpapi.amazon_product import AmazonProductProvider
from app.providers.serpapi.amazon_search import AmazonSearchProvider
from app.providers.serpapi.bing_shopping import BingShoppingProvider
from app.providers.serpapi.google_images import GoogleImagesProvider
from app.providers.serpapi.google_lens import GoogleLensProvider
from app.providers.serpapi.google_product import GoogleProductProvider
from app.providers.serpapi.google_reverse_image import GoogleReverseImageProvider
from app.providers.serpapi.google_search import GoogleSearchProvider
from app.providers.serpapi.google_shopping import GoogleShoppingProvider
from app.providers.trust.google_search_evidence import GoogleSearchEvidenceProvider
from app.providers.trust.trustpilot import TrustpilotProvider


def product_search_providers() -> list[ProductSearchProvider]:
    """Ordered by priority. Text search uses the first; others are fallbacks."""
    live = [p for p in (GoogleShoppingProvider(), BingShoppingProvider()) if p.enabled]
    return live or [DemoProductSearchProvider()]


def retailer_search_providers() -> list[RetailerSearchProvider]:
    live = [p for p in (AmazonSearchProvider(),) if p.enabled]
    return live or [DemoRetailerSearchProvider()]


def amazon_product_provider() -> ProductDetailsProvider:
    p = AmazonProductProvider()
    return p if p.enabled else DemoProductDetailsProvider()


def google_product_provider() -> ProductDetailsProvider | None:
    p = GoogleProductProvider()
    return p if p.enabled else None


def image_search_providers() -> list[ImageSearchProvider]:
    live = [p for p in (GoogleLensProvider(), GoogleReverseImageProvider()) if p.enabled]
    return live or [DemoImageSearchProvider()]


def web_search_provider() -> WebSearchProvider | None:
    p = GoogleSearchProvider()
    return p if p.enabled else None


def trust_evidence_providers() -> list[TrustEvidenceProvider]:
    providers: list[TrustEvidenceProvider] = []
    g = GoogleSearchEvidenceProvider()
    if g.enabled:
        providers.append(g)
    tp = TrustpilotProvider()
    if tp.enabled:
        providers.append(tp)
    return providers or [DemoTrustEvidenceProvider()]


def provider_status() -> dict:
    s = get_settings()
    engines = {
        "google_shopping": GoogleShoppingProvider().enabled,
        "google_product": GoogleProductProvider().enabled,
        "amazon_search": AmazonSearchProvider().enabled,
        "amazon_product": AmazonProductProvider().enabled,
        "google_search": GoogleSearchProvider().enabled,
        "google_lens": GoogleLensProvider().enabled,
        "google_images": GoogleImagesProvider().enabled,
        "bing_shopping": BingShoppingProvider().enabled,
        "google_reverse_image": GoogleReverseImageProvider().enabled,
    }
    return {
        "data_mode": s.data_mode,
        "serpapi_configured": s.serpapi_enabled,
        "engines": engines,
        "trust_evidence": [p.name for p in trust_evidence_providers()],
        "trustpilot": TrustpilotProvider().enabled,
        "ai": "openai" if s.openai_enabled else "demo",
    }
