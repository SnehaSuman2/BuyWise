"""Collect public reputation evidence about a retailer using Google Search (via SerpApi).

Search results are *evidence*, never verdicts. The Trust Engine weighs them by
source reliability, topic, sentiment and severity after analysis.
"""

from __future__ import annotations

import asyncio

from app.providers.base import EvidenceItem, ProviderResult, TrustEvidenceProvider
from app.providers.serpapi.google_search import GoogleSearchProvider

EVIDENCE_QUERIES = [
    "{name} reviews",
    "{name} complaints",
    "{name} refund",
    "{name} delivery",
    "{name} scam",
    "{name} customer service",
]


class GoogleSearchEvidenceProvider(TrustEvidenceProvider):
    name = "serpapi"
    engine = "google"

    def __init__(self, queries: list[str] | None = None, per_query: int = 8) -> None:
        self.search = GoogleSearchProvider()
        self.queries = queries or EVIDENCE_QUERIES
        self.per_query = per_query

    @property
    def enabled(self) -> bool:
        return self.search.enabled

    async def collect_evidence(
        self, retailer_name: str, domain: str | None = None
    ) -> ProviderResult[EvidenceItem]:
        if not self.enabled:
            return ProviderResult.failure(
                self.name, self.engine, "Google Search evidence provider disabled"
            )
        results = await asyncio.gather(
            *(
                self.search.search_web(q.format(name=retailer_name), max_results=self.per_query)
                for q in self.queries
            ),
            return_exceptions=True,
        )
        items: list[EvidenceItem] = []
        errors = []
        seen: set[str] = set()
        for res in results:
            if isinstance(res, Exception):
                errors.append(type(res).__name__)
                continue
            if not res.ok:
                errors.append(res.error or "error")
                continue
            for ev in res.items:
                if ev.url and ev.url in seen:
                    continue
                seen.add(ev.url or "")
                items.append(ev)
        ok = len(items) > 0 or not errors
        return ProviderResult(
            items=items,
            provider=self.name,
            engine=self.engine,
            ok=ok,
            error="; ".join(errors) or None,
        )
