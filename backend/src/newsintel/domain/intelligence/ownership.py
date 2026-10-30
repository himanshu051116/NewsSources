from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

OWNERSHIP_INDEPENDENCE_VERSION = "publisher-ownership-independence-v1"


class OwnershipRelationship(StrEnum):
    OWNED = "owned"
    SUBSIDIARY = "subsidiary"
    SISTER_BRAND = "sister_brand"
    JOINT_VENTURE = "joint_venture"
    SYNDICATION_PARTNER = "syndication_partner"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OwnershipMembership:
    publisher_id: str
    group_id: str
    relationship: OwnershipRelationship
    ownership_fraction: float | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class OwnershipIndependenceAssessment:
    methodology_version: str
    same_group: bool
    relationship: str | None
    independence_cap: float
    rationale: str


def ownership_independence_cap(
    origin_memberships: tuple[OwnershipMembership, ...],
    evidence_memberships: tuple[OwnershipMembership, ...],
    *,
    observed_at: datetime | None = None,
) -> OwnershipIndependenceAssessment:
    """Conservatively cap corroboration when publishers share ownership.

    Ownership never changes evidence stance and is never a publisher-quality signal. It only
    reduces the amount of *independent corroboration* that two commonly controlled outlets can
    contribute to the same claim.
    """

    origin = tuple(item for item in origin_memberships if _active(item, observed_at))
    evidence = tuple(item for item in evidence_memberships if _active(item, observed_at))
    pairs = [(left, right) for left in origin for right in evidence if left.group_id == right.group_id]
    if not pairs:
        return OwnershipIndependenceAssessment(
            methodology_version=OWNERSHIP_INDEPENDENCE_VERSION,
            same_group=False,
            relationship=None,
            independence_cap=1.0,
            rationale="No overlapping active ownership group was recorded for the two publishers.",
        )

    strongest = min((_pair_cap(left, right) for left, right in pairs), key=lambda item: item[0])
    cap, relationship = strongest
    return OwnershipIndependenceAssessment(
        methodology_version=OWNERSHIP_INDEPENDENCE_VERSION,
        same_group=True,
        relationship=relationship,
        independence_cap=cap,
        rationale=(
            "The publishers share an active ownership group. This only caps independent-"
            "corroboration weight; it does not imply coordination, inaccuracy, or editorial control."
        ),
    )


def _active(item: OwnershipMembership, observed_at: datetime | None) -> bool:
    if observed_at is None:
        return item.valid_to is None
    if item.valid_from is not None and observed_at < item.valid_from:
        return False
    return item.valid_to is None or observed_at <= item.valid_to


def _pair_cap(
    left: OwnershipMembership,
    right: OwnershipMembership,
) -> tuple[float, str]:
    relationships = {left.relationship, right.relationship}
    if OwnershipRelationship.OWNED in relationships or OwnershipRelationship.SUBSIDIARY in relationships:
        return 0.35, "common_control"
    if OwnershipRelationship.SISTER_BRAND in relationships:
        return 0.45, "sister_brands"
    if OwnershipRelationship.JOINT_VENTURE in relationships:
        return 0.6, "joint_venture"
    if OwnershipRelationship.SYNDICATION_PARTNER in relationships:
        return 0.65, "syndication_partner"
    return 0.7, "shared_group_unspecified"
