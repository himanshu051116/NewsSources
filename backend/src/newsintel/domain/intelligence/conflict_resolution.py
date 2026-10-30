from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

CONFLICT_RESOLVER_VERSION = "evidence-conflict-resolver-v1"


class ConflictResolutionState(StrEnum):
    RESOLVED_SUPPORT = "resolved_support"
    RESOLVED_CONTRADICTION = "resolved_contradiction"
    TEMPORAL_EVOLUTION = "temporal_evolution"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class ConflictEvidence:
    stance: str
    confidence: float
    independence_score: float
    primary_source: bool = False
    temporal_relation: str = "unknown"
    lineage_key: str | None = None
    source_key: str | None = None


@dataclass(frozen=True, slots=True)
class ConflictResolution:
    resolver_version: str
    state: ConflictResolutionState
    confidence: float
    support_weight: float
    contradiction_weight: float
    dispute_weight: float
    temporal_update_weight: float
    independent_lineage_count: int
    primary_support: bool
    primary_contradiction: bool
    rationale: str
    metadata: dict[str, object]


def resolve_evidence_conflict(
    evidence: tuple[ConflictEvidence, ...],
) -> ConflictResolution:
    grouped = _deduplicate_lineages(evidence)
    support = contradiction = dispute = temporal = 0.0
    primary_support = primary_contradiction = False
    for item in grouped:
        weight = _weight(item)
        stance = _norm(item.stance)
        if stance in {"support", "supported"}:
            support += weight
            primary_support = primary_support or item.primary_source
        elif stance in {"contradict", "contradicted", "contradiction"}:
            contradiction += weight
            primary_contradiction = primary_contradiction or item.primary_source
        elif stance in {"dispute", "disputed"}:
            dispute += weight
        elif stance in {"temporal_update", "update"}:
            temporal += weight

    decisive_total = support + contradiction
    if temporal >= 0.65 and decisive_total < 0.75:
        state = ConflictResolutionState.TEMPORAL_EVOLUTION
        confidence = min(0.95, 0.55 + 0.2 * temporal)
        rationale = (
            "Most material disagreement is explained by evidence referring to different time "
            "contexts; retain both observations as event evolution rather than forcing a contradiction."
        )
    elif support < 0.35 and contradiction < 0.35:
        state = ConflictResolutionState.INSUFFICIENT
        confidence = min(0.7, 0.2 + 0.15 * (support + contradiction + dispute + temporal))
        rationale = "There is not enough independent stance-bearing evidence for a resolution."
    elif support >= 0.55 and contradiction >= 0.55:
        dominant_ratio = max(support, contradiction) / max(0.001, min(support, contradiction))
        if dominant_ratio < 2.0 or (primary_support and primary_contradiction):
            state = ConflictResolutionState.UNRESOLVED_CONFLICT
            confidence = min(0.95, 0.58 + 0.08 * min(support, contradiction) + 0.05 * dispute)
            rationale = (
                "Material independent evidence exists on both sides. The system preserves the "
                "conflict instead of converting a close or primary-source disagreement into a binary verdict."
            )
        elif support > contradiction:
            state = ConflictResolutionState.RESOLVED_SUPPORT
            confidence = _dominance_confidence(support, contradiction, primary_support)
            rationale = "Independent supporting evidence materially outweighs contradiction evidence."
        else:
            state = ConflictResolutionState.RESOLVED_CONTRADICTION
            confidence = _dominance_confidence(contradiction, support, primary_contradiction)
            rationale = "Independent contradiction evidence materially outweighs supporting evidence."
    elif support >= max(0.55, contradiction * 2.0):
        state = ConflictResolutionState.RESOLVED_SUPPORT
        confidence = _dominance_confidence(support, contradiction, primary_support)
        rationale = "Independent supporting evidence materially outweighs contradiction evidence."
    elif contradiction >= max(0.55, support * 2.0):
        state = ConflictResolutionState.RESOLVED_CONTRADICTION
        confidence = _dominance_confidence(contradiction, support, primary_contradiction)
        rationale = "Independent contradiction evidence materially outweighs supporting evidence."
    else:
        state = ConflictResolutionState.UNRESOLVED_CONFLICT
        confidence = min(0.88, 0.45 + 0.1 * (support + contradiction + dispute))
        rationale = "Available evidence is mixed or too close to resolve safely."

    return ConflictResolution(
        resolver_version=CONFLICT_RESOLVER_VERSION,
        state=state,
        confidence=round(max(0.0, min(1.0, confidence)), 6),
        support_weight=round(support, 6),
        contradiction_weight=round(contradiction, 6),
        dispute_weight=round(dispute, 6),
        temporal_update_weight=round(temporal, 6),
        independent_lineage_count=len(grouped),
        primary_support=primary_support,
        primary_contradiction=primary_contradiction,
        rationale=rationale,
        metadata={
            "guardrail": (
                "This resolver aggregates already-assessed evidence stances. It does not infer "
                "truth from publisher identity, source popularity, or raw URL count."
            ),
            "lineage_deduplication": True,
        },
    )


def _deduplicate_lineages(evidence: tuple[ConflictEvidence, ...]) -> tuple[ConflictEvidence, ...]:
    best: dict[str, ConflictEvidence] = {}
    anonymous_counter = 0
    for item in evidence:
        key = item.lineage_key or item.source_key
        if not key:
            anonymous_counter += 1
            key = f"anonymous:{anonymous_counter}"
        current = best.get(key)
        if current is None or _weight(item) > _weight(current):
            best[key] = item
    return tuple(best[key] for key in sorted(best))


def _weight(item: ConflictEvidence) -> float:
    confidence = _score(item.confidence)
    independence = _score(item.independence_score)
    primary_factor = 1.15 if item.primary_source else 1.0
    return min(1.0, confidence * independence * primary_factor)


def _dominance_confidence(dominant: float, opposing: float, primary: bool) -> float:
    margin = dominant - opposing
    base = 0.58 + min(0.25, 0.18 * dominant) + min(0.12, 0.14 * margin)
    if primary:
        base += 0.05
    return min(0.97, base)


def _score(value: float) -> float:
    result = float(value)
    if result > 1.0:
        result /= 100.0
    return max(0.0, min(1.0, result))


def _norm(value: str) -> str:
    return "_".join(str(value).strip().casefold().replace("-", "_").split())
