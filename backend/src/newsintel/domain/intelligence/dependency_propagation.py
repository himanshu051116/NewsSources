from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

DEPENDENCY_PROPAGATION_VERSION = "correction-dependency-propagation-v1"


class DependencySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class DependentClaimImpact:
    claim_id: str
    claim_article_id: str
    via_article_id: str
    depth: int
    severity: DependencySeverity
    actions: tuple[str, ...]
    rationale: str


def classify_dependency_impact(
    *,
    correction_kind: str,
    claim_id: str,
    claim_article_id: str,
    via_article_id: str,
    depth: int,
) -> DependentClaimImpact:
    """Classify the review impact when a corrected article was used as evidence.

    This never changes a verdict. It only decides how urgently downstream analysis
    should be re-reviewed. Deeper propagation is deliberately less severe because an
    article can contain claims unrelated to the corrected passage that caused the
    upstream review.
    """

    kind = _norm(correction_kind)
    if depth < 1 or depth > 10:
        raise ValueError("dependency propagation depth must be between 1 and 10")

    if kind == "retraction":
        severity = DependencySeverity.HIGH if depth == 1 else DependencySeverity.MEDIUM
        actions = (
            "review_claim",
            "mark_verification_stale",
            "recompute_conflict",
        )
        rationale = (
            "A retracted article contributed evidence to this claim. The stored verdict is preserved, "
            "but its evidence basis requires review."
        )
    elif kind == "factual_correction":
        severity = DependencySeverity.MEDIUM if depth == 1 else DependencySeverity.LOW
        actions = (
            "review_claim",
            "mark_verification_stale",
            "recompute_conflict",
        )
        rationale = (
            "An article used as evidence received a factual correction. Re-evaluate whether the corrected "
            "passage affected this claim before relying on the prior verification."
        )
    elif kind == "clarification":
        severity = DependencySeverity.LOW
        actions = ("review_claim",)
        rationale = (
            "An evidence article was clarified. Review the dependent claim for context drift; do not infer "
            "that the prior verdict is wrong."
        )
    elif kind == "update":
        severity = DependencySeverity.LOW
        actions = ("review_claim",)
        rationale = (
            "An evidence article materially changed. Review the dependent claim only to determine whether "
            "the newer information affects its prior evidence basis."
        )
    else:
        raise ValueError(f"unsupported correction kind: {correction_kind}")

    if depth > 1:
        rationale += (
            " This is an indirect dependency propagated through another article, so impact is conservative "
            "and must be confirmed by a reviewer."
        )

    return DependentClaimImpact(
        claim_id=claim_id,
        claim_article_id=claim_article_id,
        via_article_id=via_article_id,
        depth=depth,
        severity=severity,
        actions=actions,
        rationale=rationale,
    )


def _norm(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", "_").split())
