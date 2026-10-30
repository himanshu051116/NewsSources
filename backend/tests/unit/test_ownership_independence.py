from datetime import UTC, datetime

from newsintel.domain.intelligence.ownership import (
    OwnershipMembership,
    OwnershipRelationship,
    ownership_independence_cap,
)


def test_common_control_caps_independence_without_changing_stance() -> None:
    left = OwnershipMembership("p1", "g1", OwnershipRelationship.OWNED)
    right = OwnershipMembership("p2", "g1", OwnershipRelationship.SUBSIDIARY)
    result = ownership_independence_cap((left,), (right,))
    assert result.same_group is True
    assert result.independence_cap == 0.35
    assert "corroboration" in result.rationale


def test_expired_ownership_does_not_cap_as_of_later_date() -> None:
    old = OwnershipMembership(
        "p1", "g1", OwnershipRelationship.OWNED,
        valid_to=datetime(2025, 1, 1, tzinfo=UTC),
    )
    current = OwnershipMembership("p2", "g1", OwnershipRelationship.OWNED)
    result = ownership_independence_cap(
        (old,), (current,), observed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert result.same_group is False
    assert result.independence_cap == 1.0
