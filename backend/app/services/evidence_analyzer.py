"""Turns raw evidence (search results, reviews, policies) into scored evidence.

Each item gets: topic, sentiment (-1..1), severity (0..1), confidence (0..1) and an
extracted claim. Heuristic keyword analysis runs always; when an AI provider is
configured it refines the classification but can never add evidence that was not
retrieved.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from app.providers.base import EvidenceItem
from app.providers.llm import AIProviderError, get_llm_provider

logger = logging.getLogger(__name__)

TOPIC_KEYWORDS = {
    "returns": ["return", "returns", "replacement", "exchange", "refund", "refunded", "money back"],
    "delivery": [
        "delivery",
        "delivered",
        "shipping",
        "courier",
        "late",
        "delayed",
        "arrived",
        "dispatch",
    ],
    "customer_service": [
        "customer service",
        "customer care",
        "support",
        "helpline",
        "response",
        "complaint",
        "complaints",
        "grievance",
    ],
    "authenticity": [
        "fake",
        "counterfeit",
        "genuine",
        "authentic",
        "original",
        "duplicate",
        "refurbished sold as new",
        "warranty",
    ],
    "fraud": [
        "scam",
        "fraud",
        "cheated",
        "cheating",
        "phishing",
        "never received",
        "not received",
        "stole",
        "fraudulent",
    ],
    "payment_security": [
        "payment",
        "charged twice",
        "double charged",
        "card",
        "upi",
        "cod",
        "secure checkout",
    ],
    "transparency": [
        "policy",
        "terms",
        "contact",
        "address",
        "registered",
        "grievance officer",
        "company",
        "founded",
        "established",
    ],
}
NEGATIVE = {
    "scam": 1.0,
    "fraud": 1.0,
    "cheated": 0.9,
    "fake": 0.8,
    "counterfeit": 0.9,
    "never received": 0.9,
    "not received": 0.8,
    "worst": 0.7,
    "pathetic": 0.7,
    "horrible": 0.6,
    "terrible": 0.6,
    "delayed": 0.4,
    "late": 0.3,
    "damaged": 0.5,
    "refund not": 0.8,
    "no refund": 0.8,
    "not refunded": 0.8,
    "complaint": 0.4,
    "complaints": 0.4,
    "poor": 0.4,
    "disappointed": 0.4,
    "beware": 0.7,
    "avoid": 0.6,
    "unresponsive": 0.5,
    "no response": 0.5,
    "harass": 0.7,
}
POSITIVE = {
    "genuine": 0.6,
    "authentic": 0.6,
    "trusted": 0.6,
    "reliable": 0.6,
    "excellent": 0.6,
    "great": 0.4,
    "good": 0.3,
    "fast delivery": 0.6,
    "on time": 0.5,
    "easy return": 0.7,
    "hassle-free": 0.6,
    "hassle free": 0.6,
    "quick refund": 0.7,
    "recommended": 0.5,
    "satisfied": 0.5,
    "smooth": 0.4,
    "prompt": 0.4,
    "legit": 0.6,
    "safe": 0.4,
}
# Domains whose content is primarily user complaints/reviews (higher relevance, moderate reliability)
REVIEW_DOMAINS = {
    "consumercomplaints.in": 0.65,
    "mouthshut.com": 0.6,
    "trustpilot.com": 0.7,
    "reddit.com": 0.55,
    "quora.com": 0.4,
    "sitejabber.com": 0.55,
    "glassdoor.com": 0.2,
    "twitter.com": 0.35,
    "x.com": 0.35,
    "facebook.com": 0.3,
    "complaintsboard.com": 0.55,
    "consumeraffairs.com": 0.55,
    "justdial.com": 0.4,
    "google.com": 0.4,
}
NEWS_DOMAINS = {
    "economictimes.indiatimes.com",
    "livemint.com",
    "business-standard.com",
    "thehindu.com",
    "ndtv.com",
    "moneycontrol.com",
    "indianexpress.com",
    "reuters.com",
    "timesofindia.indiatimes.com",
}


@dataclass
class AnalyzedEvidence:
    source: str
    source_type: str
    url: str | None
    title: str | None
    snippet: str | None
    published_at: datetime | None
    topic: str
    sentiment: float
    severity: float
    confidence: float
    extracted_claim: str
    is_demo: bool
    fingerprint: str


def _domain(url: str | None) -> str:
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _fingerprint(retailer_key: str, url: str | None, title: str | None, snippet: str | None) -> str:
    return hashlib.sha256(
        f"{retailer_key}|{url or ''}|{title or ''}|{(snippet or '')[:120]}".encode()
    ).hexdigest()


def _classify_topic(text: str, query: str | None) -> str:
    scores = {topic: sum(1 for kw in kws if kw in text) for topic, kws in TOPIC_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        # fall back to the query intent (e.g. "X refund") but with lower weight downstream
        q = (query or "").lower()
        for topic, kws in TOPIC_KEYWORDS.items():
            if any(kw in q for kw in kws):
                return topic
        return "general"
    return best


def _sentiment(text: str) -> tuple[float, float]:
    neg = sum(w for kw, w in NEGATIVE.items() if kw in text)
    pos = sum(w for kw, w in POSITIVE.items() if kw in text)
    if neg == 0 and pos == 0:
        return 0.0, 0.3
    raw = (pos - neg) / (pos + neg)
    severity = min(1.0, 0.3 + neg * 0.25) if neg > pos else 0.3
    return round(max(-1.0, min(1.0, raw)), 3), round(severity, 3)


def analyze_item(
    item: EvidenceItem, retailer_key: str, retailer_domain: str | None
) -> AnalyzedEvidence:
    fingerprint = _fingerprint(retailer_key, item.url, item.title, item.snippet)
    # Pre-analysed sources (policy, Trustpilot, community, demo) are used as-is.
    if item.topic and item.sentiment is not None:
        return AnalyzedEvidence(
            source=item.source,
            source_type=item.source_type,
            url=item.url,
            title=item.title,
            snippet=item.snippet,
            published_at=item.published_at,
            topic=item.topic,
            sentiment=float(item.sentiment),
            severity=float(item.severity if item.severity is not None else 0.4),
            confidence=float(item.confidence if item.confidence is not None else 0.5),
            extracted_claim=item.extracted_claim or (item.snippet or item.title or "")[:200],
            is_demo=item.is_demo,
            fingerprint=fingerprint,
        )
    text = f"{item.title or ''} {item.snippet or ''}".lower()
    topic = _classify_topic(text, item.query)
    sentiment, severity = _sentiment(text)
    domain = _domain(item.url)
    confidence = 0.35
    if domain in REVIEW_DOMAINS:
        confidence = REVIEW_DOMAINS[domain]
    elif domain in NEWS_DOMAINS:
        confidence = 0.6
    if retailer_domain and (domain == retailer_domain or domain.endswith("." + retailer_domain)):
        # Self-published pages: evidence of transparency, not of experience.
        confidence = 0.3
        if topic in ("fraud", "authenticity"):
            topic = "transparency"
            sentiment = max(sentiment, 0.2)
            severity = 0.2
    # A page merely echoing the query word ("Is X a scam?") with no strong signal is weak evidence.
    if sentiment == 0.0:
        confidence = min(confidence, 0.3)
    claim = re.sub(r"\s+", " ", (item.snippet or item.title or "")).strip()[:220]
    return AnalyzedEvidence(
        source=item.source,
        source_type=item.source_type,
        url=item.url,
        title=item.title,
        snippet=item.snippet,
        published_at=item.published_at,
        topic=topic,
        sentiment=sentiment,
        severity=severity,
        confidence=round(confidence, 3),
        extracted_claim=claim,
        is_demo=item.is_demo,
        fingerprint=fingerprint,
    )


async def refine_with_ai(
    items: list[AnalyzedEvidence], retailer_name: str
) -> list[AnalyzedEvidence]:
    """Optionally refine topic/sentiment with the AI provider. Never adds or removes items."""
    llm = get_llm_provider()
    if llm.is_demo or not items:
        return items
    batch = [i for i in items if i.source_type == "search_result"][:25]
    if not batch:
        return items
    prompt = {
        "retailer": retailer_name,
        "instructions": 'For each item classify topic (returns|delivery|customer_service|authenticity|fraud|payment_security|transparency|general), sentiment (-1..1 about the retailer, 0 if the text is not about actual customer experience), severity (0..1). Return {"items":[{"index":i,"topic":..,"sentiment":..,"severity":..,"claim":"one sentence"}]}. Do not invent facts.',
        "items": [
            {"index": idx, "title": i.title, "snippet": i.snippet, "url": i.url}
            for idx, i in enumerate(batch)
        ],
    }
    try:
        result = await llm.complete_json(
            str(prompt), system_prompt="You classify evidence about online retailers objectively."
        )
    except AIProviderError as exc:
        logger.warning("AI evidence refinement skipped: %s", exc)
        return items
    for row in result.get("items") or []:
        try:
            idx = int(row["index"])
            target = batch[idx]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        topic = row.get("topic")
        if topic in TOPIC_KEYWORDS or topic == "general":
            target.topic = topic
        try:
            target.sentiment = max(-1.0, min(1.0, float(row.get("sentiment", target.sentiment))))
            target.severity = max(0.0, min(1.0, float(row.get("severity", target.severity))))
        except (TypeError, ValueError):
            pass
        if row.get("claim"):
            target.extracted_claim = str(row["claim"])[:220]
        target.confidence = round(min(0.85, target.confidence + 0.1), 3)
    return items
