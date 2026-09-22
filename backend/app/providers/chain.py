"""Try one vendor, then the next.

BuyWise now has two search-data vendors. They are not equivalent: SerpApi
carries the immersive-product token that drives the every-store comparison, so
it is asked first and Serper answers when it cannot. Running both on every
search would spend two quotas to answer one question, so this asks in order and
stops at the first vendor that actually returns something.

A vendor that is merely out of credit fails fast through its own circuit
breaker, which is what makes falling through cheap rather than slow.
"""

from __future__ import annotations

import logging

from app.providers.base import (
    EvidenceItem,
    NormalizedListing,
    ProductSearchProvider,
    ProviderResult,
    WebSearchProvider,
)

logger = logging.getLogger(__name__)


class _Chained:
    """Shared bookkeeping: report whichever member actually answered."""

    label = "chain"

    def __init__(self, providers: list) -> None:
        self.providers = providers
        self._answered_by = providers[0] if providers else None

    @property
    def name(self) -> str:
        return getattr(self._answered_by, "name", self.label)

    @property
    def engine(self) -> str | None:
        return getattr(self._answered_by, "engine", None)

    @property
    def enabled(self) -> bool:
        return any(p.enabled for p in self.providers)

    @property
    def is_demo(self) -> bool:
        return bool(getattr(self._answered_by, "is_demo", False))

    async def _first_answer(self, call, describe: str) -> ProviderResult:
        last: ProviderResult | None = None
        for provider in self.providers:
            if not provider.enabled:
                continue
            try:
                result = await call(provider)
            except Exception as exc:  # a broken vendor must not end the chain
                logger.warning(
                    "%s %s raised %s; trying the next vendor",
                    provider.name,
                    describe,
                    type(exc).__name__,
                )
                last = ProviderResult.failure(provider.name, provider.engine, type(exc).__name__)
                continue
            self._answered_by = provider
            if result.ok and result.items:
                return result
            last = result
            if result.ok:
                logger.info(
                    "%s %s returned nothing; trying the next vendor", provider.name, describe
                )
            else:
                logger.warning("%s %s failed: %s", provider.name, describe, result.error)
        return last or ProviderResult.failure(self.label, None, "no vendor configured")


class ChainedProductSearchProvider(_Chained, ProductSearchProvider):
    label = "search"

    async def search_products(
        self, query: str, *, max_results: int = 20, min_price=None, max_price=None
    ) -> ProviderResult[NormalizedListing]:
        return await self._first_answer(
            lambda p: p.search_products(
                query, max_results=max_results, min_price=min_price, max_price=max_price
            ),
            "product search",
        )


class ChainedWebSearchProvider(_Chained, WebSearchProvider):
    label = "web_search"

    async def search_web(
        self, query: str, *, max_results: int = 10
    ) -> ProviderResult[EvidenceItem]:
        return await self._first_answer(
            lambda p: p.search_web(query, max_results=max_results), "web search"
        )
