from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from dateutil import parser as date_parser

from newsintel.domain.intelligence.claims import extract_temporal_references

TEMPORAL_REASONER_VERSION = "claim-temporal-reasoner-v1"

_AS_OF_PATTERN = re.compile(
    r"\b(?:as of|as at|by|through|up to)\s+([^,.;]{2,50})",
    re.I,
)


class TemporalRelation(StrEnum):
    SAME_WINDOW = "same_window"
    CLAIM_PRECEDES_EVIDENCE = "claim_precedes_evidence"
    EVIDENCE_PRECEDES_CLAIM = "evidence_precedes_claim"
    DISJOINT = "disjoint"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TemporalContext:
    reasoner_version: str
    asserted_at: datetime | None
    observed_at: datetime | None
    as_of: datetime | None
    event_time: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None
    temporal_references: tuple[dict[str, object], ...]
    resolution_notes: tuple[str, ...]


def derive_temporal_context(
    text: str,
    *,
    published_at: datetime | None = None,
    retrieved_at: datetime | None = None,
) -> TemporalContext:
    base = _utc(published_at) or _utc(retrieved_at)
    references = extract_temporal_references(text)
    notes: list[str] = []
    as_of = None
    match = _AS_OF_PATTERN.search(text)
    if match:
        as_of = _parse_reference(match.group(1), base)
        if as_of is not None:
            notes.append("explicit_as_of_resolved")
    event_time = None
    for item in references:
        raw = item.get("raw")
        if isinstance(raw, str):
            resolved = _parse_reference(raw, base)
            if resolved is not None:
                event_time = resolved
                notes.append("event_time_from_text")
                break
    return TemporalContext(
        reasoner_version=TEMPORAL_REASONER_VERSION,
        asserted_at=_utc(published_at),
        observed_at=_utc(retrieved_at),
        as_of=as_of,
        event_time=event_time,
        valid_from=event_time,
        valid_to=as_of,
        temporal_references=references,
        resolution_notes=tuple(notes),
    )


def compare_temporal_contexts(
    claim: TemporalContext,
    evidence: TemporalContext,
    *,
    tolerance: timedelta = timedelta(hours=24),
) -> TemporalRelation:
    claim_point = claim.as_of or claim.event_time or claim.asserted_at
    evidence_point = evidence.as_of or evidence.event_time or evidence.asserted_at
    if claim_point is None or evidence_point is None:
        return TemporalRelation.UNKNOWN
    delta = evidence_point - claim_point
    if abs(delta) <= tolerance:
        return TemporalRelation.SAME_WINDOW
    if delta > tolerance:
        return TemporalRelation.CLAIM_PRECEDES_EVIDENCE
    if delta < -tolerance:
        return TemporalRelation.EVIDENCE_PRECEDES_CLAIM
    return TemporalRelation.DISJOINT


def temporal_context_to_dict(context: TemporalContext) -> dict[str, object]:
    return {
        "reasoner_version": context.reasoner_version,
        "asserted_at": context.asserted_at.isoformat() if context.asserted_at else None,
        "observed_at": context.observed_at.isoformat() if context.observed_at else None,
        "as_of": context.as_of.isoformat() if context.as_of else None,
        "event_time": context.event_time.isoformat() if context.event_time else None,
        "valid_from": context.valid_from.isoformat() if context.valid_from else None,
        "valid_to": context.valid_to.isoformat() if context.valid_to else None,
        "temporal_references": list(context.temporal_references),
        "resolution_notes": list(context.resolution_notes),
    }


def _parse_reference(raw: str, base: datetime | None) -> datetime | None:
    value = " ".join(raw.strip().split())
    lowered = value.lower().strip(" .,;:")
    if base is not None:
        if lowered == "today":
            return base.replace(hour=0, minute=0, second=0, microsecond=0)
        if lowered == "yesterday":
            return (base - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        if lowered == "tomorrow":
            return (base + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        default = base or datetime(2000, 1, 1, tzinfo=UTC)
        parsed = date_parser.parse(value, fuzzy=True, default=default)
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
