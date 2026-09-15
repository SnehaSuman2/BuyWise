"""Trust service: collects evidence, runs the Trust Engine, persists and serves scores.

Cost control: evidence is refreshed at most once per CACHE_TTL_TRUST_SECONDS per
retailer (background job or first request), and Google Search calls are cached.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import CommunityReport, Retailer, Seller, TrustEvidence, TrustScore
from app.providers import registry
from app.providers.base import EvidenceItem
from app.schemas.common import DataMeta
from app.schemas.trust import TrustEvidenceResponse, TrustFactor, TrustScoreResponse
from app.services import trust_engine
from app.services.evidence_analyzer import AnalyzedEvidence, analyze_item, refine_with_ai

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_analyzed(row: TrustEvidence) -> AnalyzedEvidence:
    return AnalyzedEvidence(
        source=row.source,
        source_type=row.source_type,
        url=row.url,
        title=row.title,
        snippet=row.snippet,
        published_at=row.published_at,
        topic=row.topic,
        sentiment=float(row.sentiment),
        severity=float(row.severity),
        confidence=float(row.confidence),
        extracted_claim=row.extracted_claim or "",
        is_demo=row.is_demo,
        fingerprint=row.fingerprint,
    )


class TrustService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    # ------------------------------------------------------------ evidence
    async def _community_evidence(
        self, retailer_id: uuid.UUID | None, seller_id: uuid.UUID | None
    ) -> list[EvidenceItem]:
        stmt = select(CommunityReport).where(CommunityReport.moderation_status == "approved")
        stmt = (
            stmt.where(CommunityReport.seller_id == seller_id)
            if seller_id
            else stmt.where(CommunityReport.retailer_id == retailer_id)
        )
        rows = (
            (await self.db.execute(stmt.order_by(CommunityReport.created_at.desc()).limit(100)))
            .scalars()
            .all()
        )
        topic_map = {
            "purchase": "general",
            "delivery": "delivery",
            "return": "returns",
            "refund": "returns",
            "authenticity": "authenticity",
            "seller": "customer_service",
        }
        out = []
        for r in rows:
            sentiment = ((float(r.rating) - 3.0) / 2.0) if r.rating else 0.0
            out.append(
                EvidenceItem(
                    source="buywise_community",
                    source_type="verified_purchase"
                    if r.verification_status == "verified"
                    else "community_report",
                    url=None,
                    title=r.title,
                    snippet=r.body[:300],
                    published_at=r.created_at,
                    topic=topic_map.get(r.report_type, "general"),
                    sentiment=sentiment,
                    severity=0.6 if sentiment < -0.4 else 0.3,
                    confidence=0.75 if r.verification_status == "verified" else 0.5,
                    extracted_claim=(r.title or r.body[:120]),
                    is_demo=r.is_demo,
                )
            )
        return out

    async def refresh_evidence(self, retailer: Retailer) -> int:
        """Collect fresh evidence for a retailer from all enabled providers. Returns count stored."""
        items: list[EvidenceItem] = []
        for policy in trust_engine.policy_evidence(
            retailer.name, retailer.policies or {}, is_demo=False
        ):
            items.append(
                EvidenceItem(
                    source="retailer_policy",
                    source_type="policy",
                    url=policy.get("url"),
                    title=f"{retailer.name} published policy",
                    snippet=policy["claim"],
                    topic=policy["topic"],
                    sentiment=policy["sentiment"],
                    severity=policy["severity"],
                    confidence=policy["confidence"],
                    extracted_claim=policy["claim"],
                )
            )
        for provider in registry.trust_evidence_providers():
            res = await provider.collect_evidence(retailer.name, retailer.domain)
            if not res.ok:
                logger.warning(
                    "Trust evidence provider %s failed for %s: %s",
                    provider.name,
                    retailer.slug,
                    res.error,
                )
                continue
            items.extend(res.items)
        items.extend(await self._community_evidence(retailer.id, None))
        analyzed = [analyze_item(i, f"retailer:{retailer.id}", retailer.domain) for i in items]
        analyzed = await refine_with_ai(analyzed, retailer.name)
        stored = 0
        existing = set(
            (
                await self.db.execute(
                    select(TrustEvidence.fingerprint).where(
                        TrustEvidence.retailer_id == retailer.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for ev in analyzed:
            if ev.fingerprint in existing:
                continue
            self.db.add(
                TrustEvidence(
                    retailer_id=retailer.id,
                    source=ev.source,
                    source_type=ev.source_type,
                    url=ev.url,
                    title=(ev.title or "")[:500] or None,
                    snippet=ev.snippet,
                    published_at=ev.published_at,
                    topic=ev.topic,
                    sentiment=ev.sentiment,
                    severity=ev.severity,
                    confidence=ev.confidence,
                    extracted_claim=ev.extracted_claim,
                    fingerprint=ev.fingerprint,
                    collected_at=_now(),
                    is_demo=ev.is_demo,
                )
            )
            existing.add(ev.fingerprint)
            stored += 1
        await self.db.flush()
        return stored

    async def _load_evidence(
        self,
        retailer_id: uuid.UUID | None = None,
        seller_id: uuid.UUID | None = None,
        limit: int = 300,
    ) -> list[TrustEvidence]:
        stmt = select(TrustEvidence)
        stmt = (
            stmt.where(TrustEvidence.seller_id == seller_id)
            if seller_id
            else stmt.where(TrustEvidence.retailer_id == retailer_id)
        )
        if not self.settings.demo_mode:
            stmt = stmt.where(TrustEvidence.is_demo.is_(False))
        return list(
            (await self.db.execute(stmt.order_by(TrustEvidence.collected_at.desc()).limit(limit)))
            .scalars()
            .all()
        )

    # ------------------------------------------------------------ scores
    async def _latest_score(
        self, retailer_id: uuid.UUID | None = None, seller_id: uuid.UUID | None = None
    ) -> TrustScore | None:
        stmt = select(TrustScore)
        stmt = (
            stmt.where(TrustScore.seller_id == seller_id)
            if seller_id
            else stmt.where(TrustScore.retailer_id == retailer_id, TrustScore.seller_id.is_(None))
        )
        return (
            await self.db.execute(stmt.order_by(TrustScore.calculated_at.desc()).limit(1))
        ).scalar_one_or_none()

    async def compute_and_store(self, retailer: Retailer) -> TrustScore:
        rows = await self._load_evidence(retailer_id=retailer.id)
        assessment = trust_engine.assess([_to_analyzed(r) for r in rows])
        score = TrustScore(
            retailer_id=retailer.id,
            overall_score=assessment.score,
            risk_level=assessment.risk_level,
            confidence=assessment.confidence,
            confidence_level=assessment.confidence_level,
            factors=assessment.factors,
            concerns=assessment.concerns,
            component_scores=assessment.component_scores,
            evidence_count=assessment.evidence_count,
            methodology_version=assessment.methodology_version,
            explanation=assessment.explanation,
            is_demo=assessment.is_demo,
            calculated_at=_now(),
        )
        self.db.add(score)
        await self.db.flush()
        return score

    async def ensure_retailer_score(
        self, retailer: Retailer, *, refresh: bool = False
    ) -> TrustScore:
        latest = await self._latest_score(retailer_id=retailer.id)
        ttl = timedelta(seconds=self.settings.CACHE_TTL_TRUST_SECONDS)
        fresh = (
            latest is not None
            and latest.calculated_at
            and (
                _now()
                - latest.calculated_at.replace(tzinfo=latest.calculated_at.tzinfo or timezone.utc)
            )
            < ttl
        )
        if fresh and not refresh:
            return latest
        evidence_count = (
            await self.db.execute(
                select(func.count())
                .select_from(TrustEvidence)
                .where(TrustEvidence.retailer_id == retailer.id)
            )
        ).scalar_one()
        if refresh or evidence_count == 0 or not fresh:
            try:
                await self.refresh_evidence(retailer)
            except Exception as exc:  # never fail the request because evidence collection failed
                logger.warning(
                    "Evidence refresh failed for %s: %s", retailer.slug, type(exc).__name__
                )
        return await self.compute_and_store(retailer)

    async def get_retailer_trust(
        self, retailer_id: uuid.UUID, *, include_evidence: bool = True, refresh: bool = False
    ) -> TrustScoreResponse | None:
        retailer = (
            await self.db.execute(select(Retailer).where(Retailer.id == retailer_id))
        ).scalar_one_or_none()
        if retailer is None:
            return None
        score = await self.ensure_retailer_score(retailer, refresh=refresh)
        evidence = (
            await self._load_evidence(retailer_id=retailer.id, limit=40) if include_evidence else []
        )
        return self._response(score, retailer.name, "retailer", evidence)

    async def get_seller_trust(self, seller_id: uuid.UUID) -> TrustScoreResponse | None:
        seller = (
            await self.db.execute(select(Seller).where(Seller.id == seller_id))
        ).scalar_one_or_none()
        if seller is None:
            return None
        items = await self._community_evidence(None, seller.id)
        if seller.rating and seller.rating_count:
            items.append(
                EvidenceItem(
                    source="marketplace_rating",
                    source_type="review_platform",
                    title=f"{seller.name} marketplace rating",
                    snippet=f"{seller.rating}/5 from {seller.rating_count} ratings",
                    topic="general",
                    sentiment=(float(seller.rating) - 3.0) / 2.0,
                    severity=0.3,
                    confidence=min(0.7, 0.3 + seller.rating_count / 5000),
                    extracted_claim=f"Marketplace rating {seller.rating}/5 ({seller.rating_count} ratings)",
                    is_demo=seller.is_demo,
                )
            )
        analyzed = [analyze_item(i, f"seller:{seller.id}", None) for i in items]
        assessment = trust_engine.assess(analyzed)
        score = TrustScore(
            seller_id=seller.id,
            retailer_id=seller.retailer_id,
            overall_score=assessment.score,
            risk_level=assessment.risk_level,
            confidence=assessment.confidence,
            confidence_level=assessment.confidence_level,
            factors=assessment.factors,
            concerns=assessment.concerns,
            component_scores=assessment.component_scores,
            evidence_count=assessment.evidence_count,
            explanation=assessment.explanation,
            is_demo=assessment.is_demo,
            calculated_at=_now(),
        )
        return self._response(score, seller.name, "seller", [])

    async def trust_summaries(self, retailer_ids: set[uuid.UUID]) -> dict[uuid.UUID, TrustScore]:
        out: dict[uuid.UUID, TrustScore] = {}
        for rid in retailer_ids:
            retailer = (
                await self.db.execute(select(Retailer).where(Retailer.id == rid))
            ).scalar_one_or_none()
            if retailer:
                out[rid] = await self.ensure_retailer_score(retailer)
        return out

    def _response(
        self, score: TrustScore, name: str, subject_type: str, evidence: list[TrustEvidence]
    ) -> TrustScoreResponse:
        return TrustScoreResponse(
            retailer_id=score.retailer_id,
            seller_id=score.seller_id,
            subject_name=name,
            subject_type=subject_type,
            score=score.overall_score,
            risk_level=score.risk_level,
            confidence=float(score.confidence),
            confidence_level=score.confidence_level,
            explanation=score.explanation or "",
            factors=[TrustFactor(**f) for f in (score.factors or [])],
            concerns=[TrustFactor(**c) for c in (score.concerns or [])],
            component_scores=score.component_scores or {},
            evidence_count=score.evidence_count,
            evidence=[TrustEvidenceResponse.model_validate(e) for e in evidence],
            methodology_version=score.methodology_version,
            calculated_at=score.calculated_at,
            meta=DataMeta(
                data_mode="demo" if score.is_demo else "live",
                is_demo=score.is_demo,
                providers=sorted({e.source for e in evidence}),
                warnings=[
                    "Trust evidence includes simulated demo items; configure SERPAPI_API_KEY for live evidence."
                ]
                if score.is_demo
                else [],
            ),
        )
