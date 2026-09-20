"""Trust engine aggregation, explanations and independence from commercial code."""

import ast
import pathlib
from datetime import datetime, timezone

from app.providers.base import EvidenceItem
from app.services.evidence_analyzer import AnalyzedEvidence, analyze_item
from app.services.trust_engine import assess, policy_evidence


def ev(
    topic,
    sentiment,
    *,
    severity=0.3,
    confidence=0.6,
    source="google_search",
    source_type="search_result",
    demo=False,
):
    return AnalyzedEvidence(
        source=source,
        source_type=source_type,
        url=f"https://example.com/{topic}/{sentiment}",
        title=topic,
        snippet=None,
        published_at=datetime.now(timezone.utc),
        topic=topic,
        sentiment=sentiment,
        severity=severity,
        confidence=confidence,
        extracted_claim=f"{topic} claim",
        is_demo=demo,
        fingerprint=f"{topic}-{sentiment}-{severity}",
    )


def test_no_evidence_means_unknown():
    a = assess([])
    assert a.score is None and a.risk_level == "unknown" and "Not enough evidence" in a.explanation


def test_positive_evidence_low_risk_with_explanation():
    items = [
        ev("returns", 0.7),
        ev("returns", 0.6, source="trustpilot", source_type="review_platform"),
        ev("delivery", 0.6),
        ev("delivery", 0.5),
        ev("customer_service", 0.5),
        ev("authenticity", 0.6),
        ev("transparency", 0.6, source="retailer_policy", source_type="policy", confidence=0.7),
        ev("payment_security", 0.4),
    ]
    a = assess(items)
    # Eight positive items is decent but not overwhelming: a usable verdict,
    # without claiming certainty.
    assert a.score is not None and a.score >= 65
    assert a.risk_level in ("low", "medium")
    assert a.factors and all("label" in f and f["examples"] for f in a.factors)
    assert a.confidence_level in ("medium", "high")


def test_severe_fraud_evidence_caps_score_and_uses_careful_wording():
    items = [
        ev("fraud", -0.9, severity=0.9, confidence=0.7),
        ev("fraud", -0.8, severity=0.8, confidence=0.7),
        ev("returns", 0.6),
        ev("delivery", 0.6),
        ev("customer_service", 0.5),
    ]
    a = assess(items)
    assert a.score is not None and a.score <= 55
    assert a.risk_level in ("high", "unknown")
    assert "scam" not in a.explanation.lower()
    assert any(c["key"] == "fraud" for c in a.concerns)


def test_little_evidence_has_low_confidence():
    a = assess([ev("delivery", 0.9)])
    assert a.confidence <= 0.3 and a.risk_level == "unknown"


def test_demo_evidence_marks_score_demo():
    a = assess([ev("delivery", 0.5, demo=True), ev("returns", 0.5), ev("customer_service", 0.4)])
    assert a.is_demo and a.explanation.startswith("DEMO DATA")


def test_policy_evidence_generation():
    rows = policy_evidence(
        "Amazon.in",
        {
            "publishes_return_policy": True,
            "return_window_days": 7,
            "return_policy_url": "https://x",
            "cod_available": True,
        },
    )
    assert any(r["topic"] == "returns" and "7-day" in r["claim"] for r in rows)
    assert all(r["url"] for r in rows)


def test_evidence_analyzer_search_result_negative():
    item = EvidenceItem(
        source="google_search",
        source_type="search_result",
        url="https://www.consumercomplaints.in/x",
        title="Refund not received",
        snippet="Worst experience, refund not received after 30 days, cheated",
        query="X refund",
    )
    a = analyze_item(item, "r1", "x.com")
    assert a.topic in ("returns", "fraud") and a.sentiment < 0 and a.severity > 0.5
    # Surfaced by a leading query ("X refund"), so confidence is discounted — the
    # query selected for this result rather than discovering it.
    assert a.confidence < 0.3


def test_evidence_analyzer_self_published_is_weak():
    item = EvidenceItem(
        source="google_search",
        source_type="search_result",
        url="https://www.x.com/help/scam-awareness",
        title="Scam awareness",
        snippet="Beware of fraud calls",
        query="X scam",
    )
    a = analyze_item(item, "r1", "x.com")
    assert a.topic == "transparency" and a.confidence <= 0.3


def test_trust_engine_is_independent_of_commercial_modules():
    """The trust engine must not import affiliate/billing/subscription code (architectural guarantee)."""
    root = pathlib.Path(__file__).resolve().parent.parent / "app" / "services"
    for name in ("trust_engine.py", "evidence_analyzer.py", "trust_service.py"):
        tree = ast.parse((root / name).read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert not any(
                    bad in m for bad in ("affiliate", "billing", "subscription", "payments")
                ), f"{name} imports {m}"


def test_leading_queries_cannot_manufacture_a_bad_verdict():
    """Searching "<retailer> scam" returns scam pages for any brand that exists. That
    harvest is a selection artefact, not a discovery, and must be discounted — it had
    been scoring Amazon.in and Flipkart at ~29/100 "high risk" purely for being large."""
    identical = dict(
        source="google_search",
        source_type="search_result",
        url="https://www.consumercomplaints.in/x",
        title="Terrible experience",
        snippet="worst service, cheated, refund never received",
    )
    discovered = analyze_item(
        EvidenceItem(**identical, query="SomeShop reviews"), "r1", "someshop.com"
    )
    selected = analyze_item(
        EvidenceItem(**identical, query="SomeShop complaints"), "r1", "someshop.com"
    )
    assert selected.confidence < discovered.confidence


def test_retailer_own_help_pages_are_not_negative_evidence():
    """A returns FAQ or grievance contact on the retailer's own domain is the retailer
    providing a remedy, but it is dense with words the keyword scorer reads as negative."""
    a = analyze_item(
        EvidenceItem(
            source="google_search",
            source_type="search_result",
            url="https://www.amazon.in/gp/help/customer/display.html",
            title="Damaged and Defective Products - FAQ. Replacements and Refunds",
            snippet="Returns, replacements and refunds for damaged or defective products",
            query="amazon.in refund",
        ),
        "r1",
        "amazon.in",
    )
    assert a.sentiment > 0 and a.topic == "transparency"


def test_uninformative_evidence_reports_unknown_not_high_risk():
    """A score sitting on the neutral prior means we learned nothing. Calling that
    "high risk" about a real business would be wrong and unfair."""
    a = assess([ev("delivery", -0.3, confidence=0.5), ev("returns", 0.3, confidence=0.5)])
    assert a.risk_level == "unknown"
