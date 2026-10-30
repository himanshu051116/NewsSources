from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from newsintel.domain.intelligence.claims import ClaimVerificationLabel

VERIFICATION_POLICY_VERSION = "evidence-weighted-verification-v1"


class EvidenceStance(StrEnum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    DISPUTE = "dispute"
    CONTEXT = "context"
    ORIGIN = "origin"


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    stance: EvidenceStance
    independence_score: float
    evidence_quality: float = 1.0
    primary_source: bool = False
    lineage_key: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationDecision:
    label: ClaimVerificationLabel
    confidence_score: float | None
    methodology_version: str
    confidence_factors: dict[str, object]
    reasoning_trace: dict[str, object]


def verify_from_evidence(
    evidence: tuple[VerificationEvidence, ...],
    *,
    retrieval_complete: bool = False,
) -> VerificationDecision:
    """Aggregate already-classified evidence without double-counting syndicated lineages."""

    usable = [item for item in evidence if item.stance is not EvidenceStance.ORIGIN]
    deduplicated = _deduplicate_lineages(usable)
    support = _weight(deduplicated, {EvidenceStance.SUPPORT})
    contradict = _weight(deduplicated, {EvidenceStance.CONTRADICT})
    dispute = _weight(deduplicated, {EvidenceStance.DISPUTE})
    primary_support = any(
        item.primary_source and item.stance is EvidenceStance.SUPPORT for item in deduplicated
    )
    primary_contradict = any(
        item.primary_source and item.stance is EvidenceStance.CONTRADICT for item in deduplicated
    )
    independent_count = sum(item.independence_score > 0 for item in deduplicated)

    if primary_contradict and contradict >= 0.6:
        label = ClaimVerificationLabel.CONTRADICTED
        confidence = min(1.0, 0.72 + 0.18 * contradict)
        conclusion = "Primary or highly independent evidence contradicts the claim."
    elif contradict >= 1.2 and contradict > support * 1.25:
        label = ClaimVerificationLabel.CONTRADICTED
        confidence = min(1.0, 0.6 + 0.16 * contradict)
        conclusion = "Independent contradictory evidence outweighs supporting evidence."
    elif (support >= 0.8 and contradict >= 0.5) or dispute >= 0.8:
        label = ClaimVerificationLabel.DISPUTED
        balance = min(support + contradict + dispute, 2.5) / 2.5
        confidence = 0.55 + 0.3 * balance
        conclusion = "Material independent evidence is in conflict."
    elif primary_support and support >= 0.6:
        label = ClaimVerificationLabel.SUPPORTED
        confidence = min(1.0, 0.72 + 0.16 * support)
        conclusion = "Primary evidence supports the claim."
    elif support >= 1.2 and independent_count >= 2 and contradict < 0.35:
        label = ClaimVerificationLabel.SUPPORTED
        confidence = min(0.94, 0.58 + 0.18 * support)
        conclusion = "Multiple independent evidence lineages support the claim."
    elif retrieval_complete and not deduplicated:
        label = ClaimVerificationLabel.UNSUPPORTED
        confidence = 0.55
        conclusion = "A completed evidence search found no usable support or contradiction."
    else:
        label = ClaimVerificationLabel.NOT_CHECKABLE
        confidence = None
        conclusion = "Evidence is insufficient for a supported, disputed, or contradicted label."

    return VerificationDecision(
        label=label,
        confidence_score=round(confidence, 4) if confidence is not None else None,
        methodology_version=VERIFICATION_POLICY_VERSION,
        confidence_factors={
            "support_weight": round(support, 4),
            "contradict_weight": round(contradict, 4),
            "dispute_weight": round(dispute, 4),
            "independent_lineage_count": independent_count,
            "primary_support_present": primary_support,
            "primary_contradiction_present": primary_contradict,
            "retrieval_complete": retrieval_complete,
        },
        reasoning_trace={
            "conclusion": conclusion,
            "evidence_items_received": len(evidence),
            "usable_items_after_origin_filter": len(usable),
            "lineages_after_deduplication": len(deduplicated),
            "guardrail": (
                "Absence of evidence is not treated as contradiction; unsupported is emitted "
                "only when retrieval_complete is explicitly true."
            ),
        },
    )


def _deduplicate_lineages(
    evidence: list[VerificationEvidence],
) -> list[VerificationEvidence]:
    unique: dict[str, VerificationEvidence] = {}
    anonymous = 0
    for item in evidence:
        if item.lineage_key:
            key = item.lineage_key
        else:
            anonymous += 1
            key = f"anonymous:{anonymous}"
        existing = unique.get(key)
        if existing is None or _effective_weight(item) > _effective_weight(existing):
            unique[key] = item
    return list(unique.values())


def _weight(evidence: list[VerificationEvidence], stances: set[EvidenceStance]) -> float:
    return sum(_effective_weight(item) for item in evidence if item.stance in stances)


def _effective_weight(item: VerificationEvidence) -> float:
    independence = min(1.0, max(0.0, item.independence_score))
    quality = min(1.0, max(0.0, item.evidence_quality))
    primary_bonus = 1.15 if item.primary_source else 1.0
    return independence * quality * primary_bonus
