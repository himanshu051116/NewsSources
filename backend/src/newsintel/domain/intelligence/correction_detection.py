from __future__ import annotations

from dataclasses import dataclass

from newsintel.domain.intelligence.versioning import VersionChangeKind, VersionDiff

CORRECTION_DETECTION_VERSION = "article-correction-candidate-v1"


@dataclass(frozen=True, slots=True)
class CorrectionCandidate:
    suggested_kind: str
    confidence: float
    reason: str
    requires_human_confirmation: bool


def detect_correction_candidate(
    *,
    new_title: str,
    new_text: str,
    version_diff: VersionDiff,
) -> CorrectionCandidate | None:
    lowered = f"{new_title}\n{new_text}".casefold()
    retraction_markers = (
        "this article has been retracted",
        "this story has been retracted",
        "article retracted",
        "retraction notice",
        "this article has been withdrawn",
        "this story has been withdrawn",
    )
    if any(marker in lowered for marker in retraction_markers):
        return CorrectionCandidate(
            suggested_kind="retraction",
            confidence=0.99,
            reason="Explicit retraction/withdrawal language appears in the newer article version.",
            requires_human_confirmation=True,
        )
    if any(item.kind is VersionChangeKind.CORRECTION_NOTICE for item in version_diff.changes):
        kind = (
            "factual_correction"
            if version_diff.numeric_change_count or version_diff.temporal_change_count
            else "clarification"
        )
        return CorrectionCandidate(
            suggested_kind=kind,
            confidence=0.9,
            reason="The newer version contains an explicit correction/update notice with material changes.",
            requires_human_confirmation=True,
        )
    if version_diff.numeric_change_count or version_diff.temporal_change_count:
        return CorrectionCandidate(
            suggested_kind="update",
            confidence=0.68,
            reason="A material numeric or temporal assertion changed without an explicit correction notice.",
            requires_human_confirmation=True,
        )
    if version_diff.material_change_count >= 3:
        return CorrectionCandidate(
            suggested_kind="update",
            confidence=0.5,
            reason="Several material sentences changed between article versions.",
            requires_human_confirmation=True,
        )
    return None
