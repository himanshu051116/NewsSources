from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from newsintel.domain.intelligence.claims import claim_family_text, extract_temporal_references

OUTCOME_TRACKER_VERSION = "commitment-outcome-tracker-v1"


class CommitmentType(StrEnum):
    PROMISE = "promise"
    TARGET = "target"
    DEADLINE = "deadline"
    PROJECT = "project"
    POLICY = "policy"
    INVESTIGATION = "investigation"
    LEGAL_PROCESS = "legal_process"
    FORECAST = "forecast"


class OutcomeStatus(StrEnum):
    PENDING = "pending"
    ON_TRACK = "on_track"
    FULFILLED = "fulfilled"
    PARTIALLY_FULFILLED = "partially_fulfilled"
    DELAYED = "delayed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TrackableCommitment:
    commitment_key: str
    commitment_type: CommitmentType
    text: str
    actor: str | None
    deadline_text: str | None
    temporal_references: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class OutcomeAssessment:
    tracker_version: str
    status: OutcomeStatus
    confidence: float
    rationale: str
    matched_markers: tuple[str, ...]


def extract_trackable_commitment(
    claim_text: str,
    *,
    attribution: dict[str, object] | None = None,
) -> TrackableCommitment | None:
    lowered = claim_text.lower()
    patterns: list[tuple[CommitmentType, tuple[str, ...]]] = [
        (CommitmentType.PROMISE, ("promised", "pledged", "committed to")),
        (CommitmentType.TARGET, ("target", "aims to", "aimed to")),
        (CommitmentType.DEADLINE, ("will be completed", "would be completed", "deadline", "by 20")),
        (CommitmentType.PROJECT, ("will build", "will launch", "plans to build", "project would")),
        (CommitmentType.POLICY, ("will implement", "will introduce", "policy will", "plans to introduce")),
        (CommitmentType.INVESTIGATION, ("investigation", "probe will", "inquiry will")),
        (CommitmentType.LEGAL_PROCESS, ("court will", "trial will", "hearing will")),
        (CommitmentType.FORECAST, ("forecast", "projected", "expected to", "would reach")),
    ]
    commitment_type = next(
        (kind for kind, markers in patterns if any(marker in lowered for marker in markers)),
        None,
    )
    if commitment_type is None:
        return None
    actor = None
    if attribution:
        raw = attribution.get("speaker")
        if isinstance(raw, str) and raw.strip():
            actor = raw.strip()
    temporal = extract_temporal_references(claim_text)
    deadline_text = None
    match = re.search(r"\bby\s+([^,.;]{2,35})", claim_text, re.I)
    if match:
        deadline_text = " ".join(match.group(1).split())
    family = claim_family_text(claim_text)
    key_material = f"{commitment_type.value}|{actor or ''}|{family}"
    return TrackableCommitment(
        commitment_key=sha256(key_material.encode("utf-8")).hexdigest(),
        commitment_type=commitment_type,
        text=claim_text,
        actor=actor,
        deadline_text=deadline_text,
        temporal_references=temporal,
    )


def assess_outcome(
    commitment_text: str,
    evidence_text: str,
    *,
    deadline_at: datetime | None = None,
    observed_at: datetime | None = None,
) -> OutcomeAssessment:
    lowered = evidence_text.lower()
    relevance = _lexical_relevance(commitment_text, evidence_text)
    if relevance < 0.16:
        return OutcomeAssessment(
            tracker_version=OUTCOME_TRACKER_VERSION,
            status=OutcomeStatus.UNKNOWN,
            confidence=0.2,
            rationale="The supplied passage is not sufficiently related to the tracked commitment to infer an outcome.",
            matched_markers=(),
        )
    marker_groups: list[tuple[OutcomeStatus, tuple[str, ...], float]] = [
        (OutcomeStatus.CANCELLED, ("cancelled", "canceled", "scrapped", "abandoned"), 0.9),
        (OutcomeStatus.DELAYED, ("delayed", "postponed", "missed the deadline", "pushed back"), 0.86),
        (OutcomeStatus.FULFILLED, ("completed", "fulfilled", "delivered", "opened", "launched successfully", "came into force"), 0.84),
        (OutcomeStatus.PARTIALLY_FULFILLED, ("partially completed", "partly implemented", "phase one completed"), 0.82),
        (OutcomeStatus.RESOLVED, ("case closed", "final judgment", "investigation concluded", "inquiry concluded"), 0.82),
        (OutcomeStatus.ON_TRACK, ("on track", "on schedule", "progressing as planned"), 0.72),
        (OutcomeStatus.FAILED, ("failed to", "did not meet", "not achieved", "fell short"), 0.86),
    ]
    for status, markers, confidence in marker_groups:
        matched = tuple(marker for marker in markers if marker in lowered)
        if matched:
            return OutcomeAssessment(
                tracker_version=OUTCOME_TRACKER_VERSION,
                status=status,
                confidence=confidence,
                rationale=f"Outcome language matched: {', '.join(matched)}.",
                matched_markers=matched,
            )
    if deadline_at and observed_at and observed_at > deadline_at:
        return OutcomeAssessment(
            tracker_version=OUTCOME_TRACKER_VERSION,
            status=OutcomeStatus.UNKNOWN,
            confidence=0.45,
            rationale="The stated deadline has passed, but the supplied evidence does not establish completion, delay, cancellation, or failure.",
            matched_markers=(),
        )
    return OutcomeAssessment(
        tracker_version=OUTCOME_TRACKER_VERSION,
        status=OutcomeStatus.PENDING,
        confidence=0.4,
        rationale="No outcome marker was found; retain pending status rather than inferring success or failure.",
        matched_markers=(),
    )


_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "been", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "said", "that", "the", "this", "to", "was",
    "were", "will", "would",
}

def _lexical_relevance(left: str, right: str) -> float:
    def tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]{3,}", value.lower())
            if token not in _STOPWORDS
        }
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)
