"""Trust score schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import DataMeta


class EvidenceExample(BaseModel):
    claim: str | None = None
    url: str | None = None
    source: str | None = None
    sentiment: float | None = None


class TrustFactor(BaseModel):
    key: str
    label: str
    score: int | None = None
    evidence_count: int = 0
    examples: list[EvidenceExample] = []


class TrustEvidenceResponse(BaseModel):
    id: UUID
    source: str
    source_type: str
    url: str | None = None
    title: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    topic: str
    sentiment: float
    severity: float
    confidence: float
    extracted_claim: str | None = None
    collected_at: datetime
    is_demo: bool = False

    model_config = {"from_attributes": True}


class TrustScoreResponse(BaseModel):
    retailer_id: UUID | None = None
    seller_id: UUID | None = None
    subject_name: str
    subject_type: str  # retailer | seller
    score: int | None = None
    risk_level: str
    confidence: float
    confidence_level: str
    explanation: str
    factors: list[TrustFactor] = []
    concerns: list[TrustFactor] = []
    component_scores: dict[str, int | None] = {}
    evidence_count: int = 0
    evidence: list[TrustEvidenceResponse] = []
    methodology_version: str
    calculated_at: datetime
    meta: DataMeta
