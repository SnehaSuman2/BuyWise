"""Optional Trustpilot evidence provider.

Requires a legitimate Trustpilot Business API key. Disabled unless
TRUSTPILOT_ENABLED=true and TRUSTPILOT_API_KEY is set. When disabled, the Trust
Engine simply continues without it. No scraping, no fabricated data.

API reference: https://developers.trustpilot.com/ (Business Units API).
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.core.config import get_settings
from app.core.http import request_with_retry
from app.providers.base import EvidenceItem, ProviderResult, TrustEvidenceProvider

logger = logging.getLogger(__name__)
TRUSTPILOT_API = "https://api.trustpilot.com/v1"


class TrustpilotProvider(TrustEvidenceProvider):
    name = "trustpilot"
    engine = "trustpilot_business_units"

    @property
    def enabled(self) -> bool:
        return get_settings().trustpilot_enabled

    async def _get(self, path: str, params: dict | None = None) -> dict | None:
        s = get_settings()
        headers = {"apikey": s.TRUSTPILOT_API_KEY}
        if s.TRUSTPILOT_ACCESS_TOKEN:
            headers["Authorization"] = f"Bearer {s.TRUSTPILOT_ACCESS_TOKEN}"
        resp = await request_with_retry(
            "GET",
            f"{TRUSTPILOT_API}{path}",
            params=params,
            headers=headers,
            timeout=15.0,
            max_retries=1,
        )
        if resp.status_code >= 400:
            logger.warning("Trustpilot %s returned HTTP %s", path, resp.status_code)
            return None
        return resp.json()

    async def collect_evidence(
        self, retailer_name: str, domain: str | None = None
    ) -> ProviderResult[EvidenceItem]:
        if not self.enabled:
            return ProviderResult(
                items=[], provider=self.name, engine=self.engine, ok=True, error="disabled"
            )
        s = get_settings()
        try:
            unit_id = s.TRUSTPILOT_BUSINESS_UNIT_ID or None
            if not unit_id and domain:
                found = await self._get("/business-units/find", {"name": domain})
                unit_id = (found or {}).get("id")
            if not unit_id:
                return ProviderResult(
                    items=[],
                    provider=self.name,
                    engine=self.engine,
                    ok=True,
                    error="business unit not found",
                )
            unit = await self._get(f"/business-units/{unit_id}") or {}
            items: list[EvidenceItem] = []
            score = (unit.get("score") or {}).get("trustScore")
            total = (unit.get("numberOfReviews") or {}).get("total")
            if score is not None:
                sentiment = max(-1.0, min(1.0, (float(score) - 3.0) / 2.0))
                items.append(
                    EvidenceItem(
                        source="trustpilot",
                        source_type="review_platform",
                        url=f"https://www.trustpilot.com/review/{domain or unit_id}",
                        title=f"Trustpilot profile for {retailer_name}",
                        snippet=f"TrustScore {score} from {total or 'unknown number of'} reviews",
                        topic="general",
                        sentiment=sentiment,
                        severity=0.4,
                        confidence=min(0.9, 0.4 + (float(total or 0) / 5000.0)),
                        extracted_claim=f"Trustpilot TrustScore {score}/5 ({total} reviews)",
                    )
                )
            reviews = (
                await self._get(
                    f"/business-units/{unit_id}/reviews",
                    {"perPage": 20, "orderBy": "createdat.desc"},
                )
                or {}
            )
            for r in reviews.get("reviews") or []:
                stars = r.get("stars")
                if stars is None:
                    continue
                created = r.get("createdAt")
                try:
                    published = (
                        datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
                    )
                except ValueError:
                    published = None
                items.append(
                    EvidenceItem(
                        source="trustpilot",
                        source_type="review_platform",
                        url=f"https://www.trustpilot.com/reviews/{r.get('id')}",
                        title=r.get("title"),
                        snippet=(r.get("text") or "")[:500],
                        published_at=published,
                        sentiment=(float(stars) - 3.0) / 2.0,
                        severity=0.6 if stars <= 2 else 0.3,
                        confidence=0.55,
                    )
                )
            return ProviderResult(items=items, provider=self.name, engine=self.engine)
        except Exception as exc:  # network / parsing — never break the trust engine
            logger.warning("Trustpilot provider failed: %s", type(exc).__name__)
            return ProviderResult.failure(
                self.name, self.engine, f"Trustpilot unavailable: {type(exc).__name__}"
            )
