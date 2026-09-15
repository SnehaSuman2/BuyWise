"""Demo trust evidence provider — clearly simulated, used only when Google Search is unavailable."""

from __future__ import annotations

from datetime import datetime, timezone

from app.data.demo_catalog import demo_evidence_for
from app.providers.base import EvidenceItem, ProviderResult, TrustEvidenceProvider


class DemoTrustEvidenceProvider(TrustEvidenceProvider):
    name = "demo"
    engine = "demo_evidence"
    is_demo = True

    async def collect_evidence(
        self, retailer_name: str, domain: str | None = None
    ) -> ProviderResult[EvidenceItem]:
        items = [
            EvidenceItem(
                source="demo",
                source_type="search_result",
                url=e["url"],
                title=f"Demo evidence about {retailer_name}",
                snippet=e["claim"],
                published_at=datetime.now(timezone.utc),
                topic=e["topic"],
                sentiment=e["sentiment"],
                severity=e["severity"],
                confidence=e["confidence"],
                extracted_claim=e["claim"],
                is_demo=True,
            )
            for e in demo_evidence_for(retailer_name)
        ]
        return ProviderResult(items=items, provider=self.name, engine=self.engine, is_demo=True)
