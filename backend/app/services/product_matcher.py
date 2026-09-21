"""Product matching — decides whether two listings are the same product/variant.

Outputs one of:
  EXACT_MATCH, SAME_PRODUCT_DIFFERENT_VARIANT, SIMILAR_PRODUCT, UNKNOWN
with a confidence in [0, 1] and human-readable reasons.

Signals (in priority order): GTIN/EAN/UPC, ASIN, MPN/SKU, brand, model tokens,
variant attributes (storage, RAM, colour, size), generation/chip, token overlap.
A similar product is never reported as an exact match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.services.product_normalizer import NormalizedAttributes, extract_attributes

# Tokens that distinguish sibling products in a line-up (Galaxy S24 vs S24 Ultra, iPhone 15 vs 15 Pro).
LINEUP_MODIFIERS = {
    "ultra",
    "plus",
    "pro",
    "max",
    "mini",
    "lite",
    "fe",
    "neo",
    "prime",
    "air",
    "note",
    "edge",
    "fold",
    "flip",
    "se",
    "xl",
    "classic",
    "active",
    "slim",
}


class MatchType(str, Enum):
    EXACT = "exact_match"
    DIFFERENT_VARIANT = "same_product_different_variant"
    SIMILAR = "similar_product"
    UNKNOWN = "unknown"


@dataclass
class MatchResult:
    match_type: MatchType
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return {
            MatchType.EXACT: "Exact match" if self.confidence >= 0.9 else "Possible match",
            MatchType.DIFFERENT_VARIANT: "Same product, different variant",
            MatchType.SIMILAR: "Similar product",
            MatchType.UNKNOWN: "Unverified match",
        }[self.match_type]

    def as_dict(self) -> dict:
        return {
            "match_type": self.match_type.value,
            "confidence": round(self.confidence, 3),
            "label": self.label,
            "reasons": self.reasons,
        }


@dataclass
class Candidate:
    title: str
    identifiers: dict[str, str] = field(default_factory=dict)
    brand: str | None = None
    specs: dict | None = None
    _attrs: NormalizedAttributes | None = None

    @property
    def attrs(self) -> NormalizedAttributes:
        if self._attrs is None:
            self._attrs = extract_attributes(self.title, self.specs, self.brand)
        return self._attrs

    def ident(self, key: str) -> str | None:
        v = self.identifiers.get(key)
        return str(v).strip().lower() if v else None


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _brand_compatible(a: str | None, b: str | None) -> bool | None:
    if not a or not b:
        return None
    a, b = a.lower(), b.lower()
    if a == b or a in b or b in a:
        return True
    aliases = {("redmi", "xiaomi"), ("poco", "xiaomi"), ("mi", "xiaomi")}
    return (a, b) in aliases or (b, a) in aliases


def _variant_diffs(
    a: NormalizedAttributes, b: NormalizedAttributes
) -> tuple[list[str], list[str], list[str]]:
    """Return (conflicts, agreements, unknowns) over variant attributes."""
    conflicts, agreements, unknowns = [], [], []
    for key in ("storage", "ram", "color", "size"):
        va, vb = getattr(a, key), getattr(b, key)
        if va and vb:
            if key == "color":
                same = va == vb or va in vb or vb in va
            else:
                same = va == vb
            (agreements if same else conflicts).append(key)
        else:
            unknowns.append(key)
    return conflicts, agreements, unknowns


def match_products(reference: Candidate, candidate: Candidate) -> MatchResult:
    reasons: list[str] = []
    ra, ca = reference.attrs, candidate.attrs

    # 1. Hard identifiers
    for key, label, conf in (
        ("gtin", "GTIN/EAN", 0.99),
        ("asin", "ASIN", 0.98),
        ("mpn", "MPN", 0.96),
        ("sku", "SKU", 0.93),
    ):
        r, c = reference.ident(key), candidate.ident(key)
        if r and c:
            if r == c:
                reasons.append(f"{label} matches ({c.upper()})")
                return MatchResult(MatchType.EXACT, conf, reasons)
            reasons.append(f"{label} differs")
            if key in ("gtin", "asin"):
                # same family but different identifier = different variant (or different product)
                brand_ok = _brand_compatible(ra.brand, ca.brand)
                family = (
                    _jaccard(set(ra.model_tokens), set(ca.model_tokens)) > 0
                    or _jaccard(ra.tokens, ca.tokens) >= 0.5
                )
                if brand_ok is not False and family:
                    return MatchResult(
                        MatchType.DIFFERENT_VARIANT,
                        0.85,
                        reasons + ["Same product family with a different identifier"],
                    )
                return MatchResult(MatchType.SIMILAR, 0.6, reasons)

    # 2. Accessory vs product
    if ra.is_accessory != ca.is_accessory:
        reasons.append("One listing is an accessory, not the product itself")
        return MatchResult(MatchType.SIMILAR, 0.75, reasons)

    # 3. Brand
    brand_ok = _brand_compatible(ra.brand, ca.brand)
    if brand_ok is False:
        reasons.append(f"Brand differs ({ra.brand} vs {ca.brand})")
        return MatchResult(MatchType.SIMILAR, 0.7, reasons)
    if brand_ok:
        reasons.append(f"Brand matches ({ca.brand})")

    # 3b. Line-up modifiers (S24 vs S24 Ultra are different products)
    mods_r = ra.tokens & LINEUP_MODIFIERS
    mods_c = ca.tokens & LINEUP_MODIFIERS
    if mods_r != mods_c and (ra.tokens & ca.tokens):
        line = (
            f"Model line differs ({' '.join(sorted(mods_r)) or 'base'} vs "
            f"{' '.join(sorted(mods_c)) or 'base'})"
        )
        # A tier difference alone (base vs Pro Max of the SAME generation) is a
        # legitimate sibling in the line-up. This branch used to return before the
        # generation was ever compared, so "iPhone 17" vs "iPhone 15 Pro Max" — a
        # different generation that also differs in tier — was judged solely on
        # tier and came back as a 0.7-confidence sibling match. Checking generation
        # here, not just in step 5, catches that: two products that differ in BOTH
        # generation and tier are not siblings, they are simply a different phone
        # that happens to share brand and line-up words.
        if ra.generation and ca.generation and ra.generation != ca.generation:
            reasons.append(f"Generation differs ({ra.generation} vs {ca.generation})")
            reasons.append(line)
            token_sim = _jaccard(ra.tokens, ca.tokens)
            return MatchResult(
                MatchType.SIMILAR if token_sim >= 0.3 else MatchType.UNKNOWN,
                0.35 if token_sim >= 0.3 else 0.2,
                reasons,
            )
        reasons.append(line)
        return MatchResult(MatchType.SIMILAR, 0.7, reasons)

    # 4. Model tokens (hyphen-insensitive: "wh-1000xm5" == "wh1000xm5")
    r_models = {t.replace("-", "") for t in ra.model_tokens}
    c_models = {t.replace("-", "") for t in ca.model_tokens}
    model_overlap = _jaccard(r_models, c_models)
    model_match = model_overlap > 0
    if ra.model_tokens and ca.model_tokens and not model_match:
        reasons.append(
            f"Model code differs ({', '.join(ra.model_tokens[:2])} vs {', '.join(ca.model_tokens[:2])})"
        )
        token_sim = _jaccard(ra.tokens, ca.tokens)
        return MatchResult(
            MatchType.SIMILAR if token_sim >= 0.3 else MatchType.UNKNOWN,
            0.55 if token_sim >= 0.3 else 0.3,
            reasons,
        )
    if model_match:
        reasons.append("Model code matches")

    # 5. Generation / chip
    for key, label in (("generation", "Generation"), ("chip", "Chip")):
        r, c = getattr(ra, key), getattr(ca, key)
        if r and c and r != c:
            reasons.append(f"{label} differs ({r} vs {c})")
            return MatchResult(MatchType.SIMILAR, 0.7, reasons)

    # 6. Token similarity (excluding variant tokens)
    token_sim = _jaccard(ra.tokens, ca.tokens)
    conflicts, agreements, unknowns = _variant_diffs(ra, ca)
    strong_family = model_match or token_sim >= 0.55 or (brand_ok and token_sim >= 0.4)

    if not strong_family:
        if token_sim >= 0.3:
            reasons.append(f"Titles partially overlap ({int(token_sim * 100)}%)")
            return MatchResult(MatchType.SIMILAR, 0.5, reasons)
        reasons.append("Insufficient overlap to identify the product")
        return MatchResult(MatchType.UNKNOWN, 0.2, reasons)

    # 7. Variant attributes
    if conflicts:
        pretty = ", ".join(f"{k}: {getattr(ra, k)} vs {getattr(ca, k)}" for k in conflicts)
        reasons.append(f"Variant differs ({pretty})")
        return MatchResult(
            MatchType.DIFFERENT_VARIANT, min(0.95, 0.75 + 0.1 * len(agreements)), reasons
        )

    confidence = 0.6 + 0.2 * token_sim + (0.1 if model_match else 0.0)
    confidence += 0.04 * len(agreements)
    if agreements:
        reasons.append("Variant attributes match (" + ", ".join(agreements) + ")")
    # penalise missing variant info that matters for this product family
    relevant_unknown = [u for u in unknowns if getattr(ra, u) or getattr(ca, u)]
    if relevant_unknown:
        confidence -= 0.08 * len(relevant_unknown)
        reasons.append("Some variant details not stated (" + ", ".join(relevant_unknown) + ")")
    confidence = max(0.5, min(0.97, confidence))
    return MatchResult(MatchType.EXACT, round(confidence, 3), reasons)


def quick_match(
    reference_title: str,
    candidate_title: str,
    ref_ids: dict | None = None,
    cand_ids: dict | None = None,
) -> MatchResult:
    return match_products(
        Candidate(reference_title, ref_ids or {}), Candidate(candidate_title, cand_ids or {})
    )
