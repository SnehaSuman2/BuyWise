"""BuyWise Trust Engine.

Aggregates analysed evidence into a 0–100 Trust Score with a risk level, a
confidence level and an explanation. Pure computation; persistence lives in
trust_service.

INDEPENDENCE GUARANTEE: this module imports nothing from billing, affiliate or
subscription code and receives only evidence. Commercial relationships cannot
influence the score. A test enforces the import boundary.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.evidence_analyzer import AnalyzedEvidence

METHODOLOGY_VERSION = "1.0"

FACTOR_WEIGHTS = {
    "returns": 0.20,
    "delivery": 0.18,
    "customer_service": 0.15,
    "authenticity": 0.15,
    "fraud": 0.12,
    "transparency": 0.12,
    "payment_security": 0.08,
}
FACTOR_LABELS = {
    "returns": "Returns & refunds",
    "delivery": "Delivery reliability",
    "customer_service": "Customer service",
    "authenticity": "Product authenticity",
    "fraud": "Fraud & complaint patterns",
    "transparency": "Business transparency",
    "payment_security": "Payment security",
    "general": "Overall customer experience",
}
SOURCE_RELIABILITY = {
    "verified_purchase": 1.0,
    "policy": 0.95,
    "review_platform": 0.75,
    "community_report": 0.55,
    "search_result": 0.5,
}
PRIOR_SCORE = 50.0
# Pseudo-evidence pulling towards neutral. Set high enough that a thin or skewed
# evidence pool cannot swing the score to an extreme — BuyWise should say "we don't
# know" rather than assert a large, established retailer is high risk on the strength
# of a handful of search hits.
PRIOR_WEIGHT = 0.5
SENTIMENT_SCALE = 65.0  # mean sentiment of +0.5 → ~80, -0.5 → ~20


@dataclass
class TrustAssessment:
    score: int | None
    risk_level: str
    confidence: float
    confidence_level: str
    factors: list[dict] = field(default_factory=list)
    concerns: list[dict] = field(default_factory=list)
    component_scores: dict[str, int | None] = field(default_factory=dict)
    evidence_count: int = 0
    explanation: str = ""
    is_demo: bool = False
    methodology_version: str = METHODOLOGY_VERSION

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "factors": self.factors,
            "concerns": self.concerns,
            "component_scores": self.component_scores,
            "evidence_count": self.evidence_count,
            "explanation": self.explanation,
            "is_demo": self.is_demo,
            "methodology_version": self.methodology_version,
        }


def _recency_weight(published_at: datetime | None, now: datetime) -> float:
    if not published_at:
        return 0.8
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - published_at).days)
    return 0.4 + 0.6 * math.exp(-age_days / 365.0)


def _evidence_weight(ev: AnalyzedEvidence, now: datetime) -> float:
    return (
        ev.confidence
        * SOURCE_RELIABILITY.get(ev.source_type, 0.4)
        * _recency_weight(ev.published_at, now)
    )


def assess(evidence: list[AnalyzedEvidence], now: datetime | None = None) -> TrustAssessment:
    now = now or datetime.now(timezone.utc)
    evidence = [e for e in evidence if e.sentiment is not None]
    is_demo = any(
        e.is_demo for e in evidence
    )  # any simulated evidence marks the whole score as demo
    if not evidence:
        return TrustAssessment(
            score=None,
            risk_level="unknown",
            confidence=0.0,
            confidence_level="low",
            evidence_count=0,
            explanation="Not enough evidence to confidently assess this retailer yet.",
        )

    # --- per-factor aggregation
    per_topic: dict[str, list[tuple[float, float, float]]] = {}
    for ev in evidence:
        per_topic.setdefault(ev.topic, []).append(
            (ev.sentiment, _evidence_weight(ev, now), ev.severity)
        )
    component: dict[str, int | None] = {}
    coverage: dict[str, float] = {}
    for topic in FACTOR_WEIGHTS:
        rows = per_topic.get(topic, []) + (
            [] if topic != "customer_service" else per_topic.get("general", [])
        )
        if not rows:
            component[topic] = None
            coverage[topic] = 0.0
            continue
        w_sum = sum(w for _, w, _ in rows)
        # severity amplifies negative evidence
        adj = sum(s * w * (1 + sev if s < 0 else 1) for s, w, sev in rows)
        mean_sent = adj / (w_sum + PRIOR_WEIGHT)
        component[topic] = int(round(max(0, min(100, PRIOR_SCORE + SENTIMENT_SCALE * mean_sent))))
        coverage[topic] = min(1.0, w_sum / 1.0)

    # --- overall
    covered = {t: s for t, s in component.items() if s is not None}
    if covered:
        w_total = sum(FACTOR_WEIGHTS[t] * (0.5 + 0.5 * coverage[t]) for t in covered)
        overall = (
            sum(component[t] * FACTOR_WEIGHTS[t] * (0.5 + 0.5 * coverage[t]) for t in covered)
            / w_total
        )
    else:
        overall = PRIOR_SCORE
    # severe fraud evidence caps the score
    fraud_rows = per_topic.get("fraud", [])
    severe_fraud = sum(w for s, w, sev in fraud_rows if s < -0.5 and sev >= 0.7)
    if severe_fraud >= 1.0:
        overall = min(overall, 45.0)
    elif severe_fraud >= 0.5:
        overall = min(overall, 54.0)
    score = int(round(max(0, min(100, overall))))

    # --- confidence: quantity, source diversity, factor coverage
    total_weight = sum(_evidence_weight(e, now) for e in evidence)
    sources = {e.source for e in evidence}
    factor_cov = sum(1 for t in FACTOR_WEIGHTS if coverage.get(t, 0) > 0.2) / len(FACTOR_WEIGHTS)
    confidence = min(
        1.0,
        0.15
        + min(total_weight, 6) / 6 * 0.45
        + min(len(sources), 3) / 3 * 0.15
        + factor_cov * 0.25,
    )
    if len(evidence) < 3:
        confidence = min(confidence, 0.3)
    if is_demo:
        confidence = min(confidence, 0.6)
    confidence = round(confidence, 2)
    level = "high" if confidence >= 0.7 else "medium" if confidence >= 0.45 else "low"

    # --- factors & concerns with explanations
    factors, concerns = [], []
    for topic, s in component.items():
        if s is None:
            continue
        rows = [
            e
            for e in evidence
            if e.topic == topic or (topic == "customer_service" and e.topic == "general")
        ]
        supporting = sorted(rows, key=lambda e: -abs(e.sentiment) * e.confidence)[:3]
        entry = {
            "key": topic,
            "label": FACTOR_LABELS[topic],
            "score": s,
            "evidence_count": len(rows),
            "examples": [
                {
                    "claim": e.extracted_claim,
                    "url": e.url,
                    "source": e.source,
                    "sentiment": e.sentiment,
                }
                for e in supporting
            ],
        }
        if s >= 65 and coverage[topic] >= 0.2:
            factors.append(entry)
        elif s <= 55 or any(e.sentiment <= -0.5 and e.severity >= 0.6 for e in rows):
            concerns.append(entry)
    # explicit policy facts are positive factors regardless of score
    policy_rows = [e for e in evidence if e.source_type == "policy" and e.sentiment > 0]
    if policy_rows and not any(f["key"] == "transparency" for f in factors):
        factors.append(
            {
                "key": "transparency",
                "label": FACTOR_LABELS["transparency"],
                "score": component.get("transparency"),
                "evidence_count": len(policy_rows),
                "examples": [
                    {
                        "claim": e.extracted_claim,
                        "url": e.url,
                        "source": e.source,
                        "sentiment": e.sentiment,
                    }
                    for e in policy_rows[:3]
                ],
            }
        )

    # A score sitting on the neutral prior means the evidence did not discriminate —
    # that is "we don't know", not "high risk". Reporting an established retailer as
    # high risk because search hits netted out to neutral would be both wrong and
    # unfair to a real business, which is exactly what BuyWise must not do.
    uninformative = abs(score - PRIOR_SCORE) <= 6

    # Calling a real business "high risk" is a serious, publishable accusation, so it
    # requires corroboration rather than an aggregate dipping below a threshold. At
    # least three independent, confident, high-severity negative items — and public
    # search noise about any large retailer does not qualify, because leading queries
    # are already discounted to low confidence upstream.
    corroborated_negatives = sum(
        1 for e in evidence if e.sentiment <= -0.5 and e.severity >= 0.6 and e.confidence >= 0.5
    )
    if confidence < 0.4 or uninformative:
        risk = "unknown"
    elif score >= 75:
        risk = "low"
    elif score >= 55:
        risk = "medium"
    elif corroborated_negatives >= 3:
        risk = "high"
    else:
        risk = "medium"

    if risk == "unknown":
        explanation = (
            "Not enough discriminating evidence to rate this retailer yet. Public search "
            "results about any large retailer skew negative, so BuyWise withholds a "
            "verdict rather than inferring one."
            if uninformative
            else "Insufficient evidence to confidently assess this retailer. The score below is provisional."
        )
    elif risk == "high":
        explanation = (
            f"Higher risk based on available evidence, including {corroborated_negatives} "
            "corroborated reports of serious problems. Review the concerns before buying."
        )
    elif risk == "medium":
        explanation = "Mixed evidence. Generally usable, but check the concerns listed."
    else:
        explanation = (
            "Evidence is mostly positive across returns, delivery and customer experience."
        )
    if is_demo:
        explanation = "DEMO DATA — " + explanation

    return TrustAssessment(
        score=score,
        risk_level=risk,
        confidence=confidence,
        confidence_level=level,
        factors=factors,
        concerns=concerns,
        component_scores=component,
        evidence_count=len(evidence),
        explanation=explanation,
        is_demo=is_demo,
    )


def policy_evidence(retailer_name: str, policies: dict, is_demo: bool = False) -> list[dict]:
    """Convert curated policy facts into pre-analysed evidence dicts (source_type=policy)."""
    out = []
    src = policies.get("return_policy_url") or policies.get("buyer_protection_url")
    if policies.get("publishes_return_policy"):
        days = policies.get("return_window_days")
        out.append(
            {
                "topic": "returns",
                "sentiment": 0.5 if days else 0.3,
                "severity": 0.2,
                "confidence": 0.7,
                "claim": "Publishes a returns policy"
                + (f" ({days}-day window on eligible items)" if days else ""),
                "url": src,
            }
        )
    if policies.get("buyer_protection"):
        out.append(
            {
                "topic": "returns",
                "sentiment": 0.5,
                "severity": 0.2,
                "confidence": 0.7,
                "claim": f"Offers buyer protection: {policies['buyer_protection']}",
                "url": policies.get("buyer_protection_url") or src,
            }
        )
    if policies.get("grievance_officer_published"):
        out.append(
            {
                "topic": "transparency",
                "sentiment": 0.5,
                "severity": 0.2,
                "confidence": 0.7,
                "claim": "Publishes a grievance officer contact as required by Indian consumer rules",
                "url": src,
            }
        )
    if policies.get("cod_available"):
        out.append(
            {
                "topic": "payment_security",
                "sentiment": 0.3,
                "severity": 0.2,
                "confidence": 0.6,
                "claim": "Cash on delivery available, reducing prepayment risk",
                "url": src,
            }
        )
    established = policies.get("established_year_in_india")
    if established:
        years = 2026 - int(established)
        out.append(
            {
                "topic": "transparency",
                "sentiment": min(0.7, 0.3 + years / 40),
                "severity": 0.2,
                "confidence": 0.85,
                "claim": f"Operating in India since {established} ({years} years)"
                + (
                    f", part of {policies['parent_company']}"
                    if policies.get("parent_company")
                    else ""
                ),
                "url": src,
            }
        )
    if policies.get("verified_purchase_reviews"):
        out.append(
            {
                "topic": "authenticity",
                "sentiment": 0.5,
                "severity": 0.2,
                "confidence": 0.8,
                "claim": "Reviews on this platform are marked as verified purchases",
                "url": src,
            }
        )
    if policies.get("authorised_sellers_only"):
        out.append(
            {
                "topic": "authenticity",
                "sentiment": 0.6,
                "severity": 0.2,
                "confidence": 0.8,
                "claim": "Sells only through brand-authorised sellers",
                "url": src,
            }
        )
    if policies.get("customer_support_published"):
        out.append(
            {
                "topic": "customer_service",
                "sentiment": 0.4,
                "severity": 0.2,
                "confidence": 0.75,
                "claim": "Publishes customer support contact channels",
                "url": src,
            }
        )
    if policies.get("physical_stores"):
        out.append(
            {
                "topic": "transparency",
                "sentiment": 0.4,
                "severity": 0.2,
                "confidence": 0.65,
                "claim": "Operates physical stores in India",
                "url": src,
            }
        )
    if not out:
        out.append(
            {
                "topic": "transparency",
                "sentiment": 0.0,
                "severity": 0.3,
                "confidence": 0.3,
                "claim": f"No curated policy information for {retailer_name} yet",
                "url": None,
            }
        )
    for o in out:
        o["is_demo"] = is_demo
    return out
