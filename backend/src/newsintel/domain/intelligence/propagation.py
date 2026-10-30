from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

CORRECTION_PROPAGATION_VERSION = "correction-propagation-v1"


class CorrectionKind(StrEnum):
    UPDATE = "update"
    CLARIFICATION = "clarification"
    FACTUAL_CORRECTION = "factual_correction"
    RETRACTION = "retraction"


class PropagationAction(StrEnum):
    RECORD_ONLY = "record_only"
    REVIEW_CLAIM = "review_claim"
    MARK_VERIFICATION_STALE = "mark_verification_stale"
    RECOMPUTE_CONFLICT = "recompute_conflict"
    REBUILD_EVENT_GRAPH = "rebuild_event_graph"
    RECOMPUTE_RELIABILITY = "recompute_reliability"
    INVALIDATE_SOURCE_EVIDENCE = "invalidate_source_evidence"


@dataclass(frozen=True, slots=True)
class CorrectionImpact:
    claim_id: str
    actions: tuple[PropagationAction, ...]
    severity: str
    rationale: str


@dataclass(frozen=True, slots=True)
class CorrectionPropagationPlan:
    methodology_version: str
    correction_kind: CorrectionKind
    impacts: tuple[CorrectionImpact, ...]
    event_actions: tuple[PropagationAction, ...]
    publisher_actions: tuple[PropagationAction, ...]
    automatic_verdict_change: bool
    interpretation: str


def plan_correction_propagation(
    correction_kind: str,
    affected_claim_ids: tuple[str, ...],
) -> CorrectionPropagationPlan:
    kind = CorrectionKind(_norm(correction_kind))
    claim_ids = tuple(dict.fromkeys(value.strip() for value in affected_claim_ids if value.strip()))
    impacts: list[CorrectionImpact] = []

    for claim_id in claim_ids:
        if kind is CorrectionKind.RETRACTION:
            actions = (
                PropagationAction.REVIEW_CLAIM,
                PropagationAction.MARK_VERIFICATION_STALE,
                PropagationAction.INVALIDATE_SOURCE_EVIDENCE,
                PropagationAction.RECOMPUTE_CONFLICT,
            )
            severity = "critical"
            rationale = "The source article was retracted; dependent evidence must be re-reviewed."
        elif kind is CorrectionKind.FACTUAL_CORRECTION:
            actions = (
                PropagationAction.REVIEW_CLAIM,
                PropagationAction.MARK_VERIFICATION_STALE,
                PropagationAction.RECOMPUTE_CONFLICT,
            )
            severity = "high"
            rationale = "A factual correction can invalidate a prior claim/evidence interpretation."
        elif kind is CorrectionKind.CLARIFICATION:
            actions = (PropagationAction.REVIEW_CLAIM, PropagationAction.RECOMPUTE_CONFLICT)
            severity = "medium"
            rationale = "A clarification may alter context without necessarily reversing the factual claim."
        else:
            actions = (PropagationAction.RECORD_ONLY,)
            severity = "low"
            rationale = "An ordinary update is retained historically and does not invalidate earlier evidence by itself."
        impacts.append(CorrectionImpact(claim_id, actions, severity, rationale))

    event_actions = (
        (PropagationAction.REBUILD_EVENT_GRAPH,)
        if kind is not CorrectionKind.UPDATE or claim_ids
        else (PropagationAction.RECORD_ONLY,)
    )
    publisher_actions = (
        (PropagationAction.RECOMPUTE_RELIABILITY,)
        if kind in {CorrectionKind.FACTUAL_CORRECTION, CorrectionKind.RETRACTION}
        else ()
    )
    return CorrectionPropagationPlan(
        methodology_version=CORRECTION_PROPAGATION_VERSION,
        correction_kind=kind,
        impacts=tuple(impacts),
        event_actions=event_actions,
        publisher_actions=publisher_actions,
        automatic_verdict_change=False,
        interpretation=(
            "Corrections and retractions invalidate assumptions and trigger re-review; they do not "
            "silently rewrite historical verification labels. New verification revisions must be created explicitly."
        ),
    )


def _norm(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", "_").split())
