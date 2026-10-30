from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from newsintel.domain.intelligence.claims import extract_quantities
from newsintel.domain.intelligence.evidence import (
    EvidencePassage,
    EvidencePassageRelationship,
    find_evidence_passages,
)
from newsintel.domain.intelligence.temporal import (
    TemporalRelation,
    compare_temporal_contexts,
    derive_temporal_context,
    temporal_context_to_dict,
)

STANCE_ASSESSOR_VERSION = "passage-stance-temporal-v1"


class PassageStance(StrEnum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    DISPUTE = "dispute"
    CONTEXT = "context"
    TEMPORAL_UPDATE = "temporal_update"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class StanceAssessment:
    assessor_version: str
    stance: PassageStance
    confidence: float
    best_passage: EvidencePassage | None
    temporal_relation: TemporalRelation
    rationale: str
    metadata: dict[str, object]


def assess_evidence_stance(
    claim_text: str,
    evidence_text: str,
    *,
    claim_published_at: datetime | None = None,
    evidence_published_at: datetime | None = None,
    evidence_retrieved_at: datetime | None = None,
) -> StanceAssessment:
    passages = find_evidence_passages(claim_text, evidence_text, max_passages=5)
    claim_temporal = derive_temporal_context(claim_text, published_at=claim_published_at)
    evidence_temporal = derive_temporal_context(
        evidence_text,
        published_at=evidence_published_at,
        retrieved_at=evidence_retrieved_at,
    )
    temporal_relation = compare_temporal_contexts(claim_temporal, evidence_temporal)
    if not passages:
        return StanceAssessment(
            assessor_version=STANCE_ASSESSOR_VERSION,
            stance=PassageStance.INSUFFICIENT,
            confidence=0.0,
            best_passage=None,
            temporal_relation=temporal_relation,
            rationale="No passage crossed the deterministic relevance threshold.",
            metadata=_metadata(claim_temporal, evidence_temporal, passages),
        )
    best = passages[0]
    negation_flip = _negation_mismatch(claim_text, best.text)
    if best.relationship is EvidencePassageRelationship.POTENTIAL_NUMERIC_CONFLICT:
        if temporal_relation in {
            TemporalRelation.CLAIM_PRECEDES_EVIDENCE,
            TemporalRelation.EVIDENCE_PRECEDES_CLAIM,
        }:
            stance = PassageStance.TEMPORAL_UPDATE
            confidence = 0.76
            rationale = "The values differ, but the statements refer to materially different time contexts; treat this as an update until same-time evidence shows a contradiction."
        else:
            stance = PassageStance.CONTRADICT
            confidence = 0.82
            rationale = "A highly related passage reports a different normalized quantity in the same or unresolved time context."
    elif best.relationship is EvidencePassageRelationship.POTENTIAL_TEMPORAL_CONFLICT:
        stance = PassageStance.DISPUTE
        confidence = 0.72
        rationale = "A highly related passage gives a different date/time assertion; this requires source-level adjudication."
    elif negation_flip:
        stance = PassageStance.CONTRADICT
        confidence = 0.78
        rationale = "The most relevant passage reverses the claim's polarity through explicit negation."
    elif best.relationship is EvidencePassageRelationship.MATCHING_ASSERTION:
        stance = PassageStance.SUPPORT
        confidence = min(0.96, 0.62 + 0.25 * max(best.similarity_score, best.lexical_overlap))
        rationale = "The most relevant passage makes a materially matching assertion with no detected normalized numeric/temporal conflict."
    elif best.relationship is EvidencePassageRelationship.RELATED_CONTEXT:
        stance = PassageStance.CONTEXT
        confidence = 0.58
        rationale = "The passage is related context but does not independently establish the proposition."
    else:
        stance = PassageStance.INSUFFICIENT
        confidence = 0.25
        rationale = "The evidence passage is too weakly related to determine stance."
    return StanceAssessment(
        assessor_version=STANCE_ASSESSOR_VERSION,
        stance=stance,
        confidence=round(confidence, 4),
        best_passage=best,
        temporal_relation=temporal_relation,
        rationale=rationale,
        metadata={
            **_metadata(claim_temporal, evidence_temporal, passages),
            "negation_mismatch": negation_flip,
            "claim_quantities": list(extract_quantities(claim_text)),
            "evidence_quantities": list(extract_quantities(best.text)),
        },
    )


def _negation_mismatch(claim_text: str, passage: str) -> bool:
    pattern = re.compile(r"\b(?:not|never|no longer|didn't|did not|hasn't|has not|isn't|is not|wasn't|was not|denied)\b", re.I)
    return bool(pattern.search(claim_text)) != bool(pattern.search(passage))


def _metadata(claim_temporal, evidence_temporal, passages) -> dict[str, object]:
    return {
        "claim_temporal_context": temporal_context_to_dict(claim_temporal),
        "evidence_temporal_context": temporal_context_to_dict(evidence_temporal),
        "candidate_passage_count": len(passages),
    }
