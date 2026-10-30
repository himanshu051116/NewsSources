from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

SEARCH_STOPPING_VERSION = "evidence-search-stopping-v1"


class SearchDecision(StrEnum):
    CONTINUE = "continue"
    STOP_SUFFICIENT = "stop_sufficient"
    STOP_EXHAUSTED = "stop_exhausted"
    STOP_BUDGET = "stop_budget"
    ESCALATE_CONFLICT = "escalate_conflict"


@dataclass(frozen=True, slots=True)
class SearchRoundObservation:
    round_number: int
    authorities_attempted: int
    documents_retrieved: int
    new_lineages: int
    new_primary_records: int
    covered_evidence_classes: tuple[str, ...] = ()
    authority_exhausted: bool = False


@dataclass(frozen=True, slots=True)
class SearchStoppingAssessment:
    methodology_version: str
    decision: SearchDecision
    completeness_score: float
    covered_evidence_classes: tuple[str, ...]
    uncovered_evidence_classes: tuple[str, ...]
    independent_lineages: int
    primary_records: int
    rounds_completed: int
    rationale: str
    metadata: dict[str, object]


def assess_evidence_search_stopping(
    required_evidence_classes: tuple[str, ...],
    rounds: tuple[SearchRoundObservation, ...],
    *,
    independent_lineages: int,
    primary_records: int,
    conflict_state: str | None = None,
    max_rounds: int = 4,
    min_independent_lineages: int = 2,
    require_primary_record: bool = True,
) -> SearchStoppingAssessment:
    if max_rounds < 1 or max_rounds > 20:
        raise ValueError("max_rounds must be between 1 and 20")
    if min_independent_lineages < 0 or min_independent_lineages > 20:
        raise ValueError("min_independent_lineages must be between 0 and 20")

    required = tuple(dict.fromkeys(_norm(item) for item in required_evidence_classes if _norm(item)))
    covered_set: set[str] = set()
    for item in rounds:
        covered_set.update(_norm(value) for value in item.covered_evidence_classes if _norm(value))
    covered = tuple(item for item in required if item in covered_set)
    uncovered = tuple(item for item in required if item not in covered_set)
    coverage = len(covered) / len(required) if required else 1.0
    lineage_ratio = min(1.0, independent_lineages / max(1, min_independent_lineages))
    primary_ratio = 1.0 if (not require_primary_record or primary_records > 0) else 0.0
    completeness = round(0.5 * coverage + 0.3 * lineage_ratio + 0.2 * primary_ratio, 6)
    rounds_completed = max((item.round_number for item in rounds), default=0)
    recent = sorted(rounds, key=lambda item: item.round_number)[-2:]
    no_recent_yield = bool(recent) and all(
        item.documents_retrieved == 0 and item.new_lineages == 0 and item.new_primary_records == 0
        for item in recent
    )
    exhausted = bool(rounds) and all(item.authority_exhausted for item in recent)
    conflict = _norm(conflict_state)

    if conflict == "unresolved_conflict" and primary_records > 0 and independent_lineages >= 2:
        decision = SearchDecision.ESCALATE_CONFLICT
        rationale = (
            "Material independent evidence remains in conflict after primary evidence was found. "
            "Escalate for adjudication rather than spending the remaining search budget mechanically."
        )
    elif not uncovered and independent_lineages >= min_independent_lineages and (
        not require_primary_record or primary_records > 0
    ) and rounds_completed >= 1:
        decision = SearchDecision.STOP_SUFFICIENT
        rationale = (
            "Required evidence classes are covered and the configured independent/primary evidence "
            "minimums are met. Stopping here limits redundant retrieval without implying factual certainty."
        )
    elif rounds_completed >= max_rounds:
        decision = SearchDecision.STOP_BUDGET
        rationale = (
            "The configured evidence-search round budget is exhausted. Remaining coverage gaps are "
            "reported explicitly and must not be interpreted as contradiction."
        )
    elif (exhausted or no_recent_yield) and rounds_completed >= 2:
        decision = SearchDecision.STOP_EXHAUSTED
        rationale = (
            "Recent search rounds produced no new evidence lineages or primary records, or all selected "
            "authorities reported exhaustion. The unresolved gaps are preserved for analyst review."
        )
    else:
        decision = SearchDecision.CONTINUE
        rationale = (
            "Evidence coverage, independence, or primary-record requirements remain incomplete and the "
            "configured search budget still permits another round."
        )

    return SearchStoppingAssessment(
        methodology_version=SEARCH_STOPPING_VERSION,
        decision=decision,
        completeness_score=completeness,
        covered_evidence_classes=covered,
        uncovered_evidence_classes=uncovered,
        independent_lineages=max(0, int(independent_lineages)),
        primary_records=max(0, int(primary_records)),
        rounds_completed=rounds_completed,
        rationale=rationale,
        metadata={
            "coverage_ratio": round(coverage, 6),
            "min_independent_lineages": min_independent_lineages,
            "require_primary_record": require_primary_record,
            "max_rounds": max_rounds,
            "no_recent_yield": no_recent_yield,
            "recent_authorities_exhausted": exhausted,
            "conflict_state": conflict or None,
            "guardrail": "Search completeness is not factual truth confidence.",
        },
    )


def _norm(value: str | None) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())
