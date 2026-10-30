from newsintel.domain.intelligence.conflict_resolution import (
    ConflictEvidence,
    ConflictResolutionState,
    resolve_evidence_conflict,
)


def test_temporal_updates_are_not_forced_into_contradiction() -> None:
    result = resolve_evidence_conflict(
        (
            ConflictEvidence("temporal_update", 0.9, 1.0, lineage_key="official-1"),
            ConflictEvidence("temporal_update", 0.8, 0.9, lineage_key="wire-1"),
        )
    )
    assert result.state is ConflictResolutionState.TEMPORAL_EVOLUTION
    assert result.temporal_update_weight > 1.0


def test_material_primary_conflict_remains_unresolved() -> None:
    result = resolve_evidence_conflict(
        (
            ConflictEvidence("support", 0.95, 1.0, primary_source=True, lineage_key="agency-a"),
            ConflictEvidence("contradict", 0.94, 1.0, primary_source=True, lineage_key="agency-b"),
        )
    )
    assert result.state is ConflictResolutionState.UNRESOLVED_CONFLICT
    assert result.primary_support is True
    assert result.primary_contradiction is True


def test_same_lineage_cannot_multiply_support() -> None:
    result = resolve_evidence_conflict(
        (
            ConflictEvidence("support", 0.9, 1.0, lineage_key="wire"),
            ConflictEvidence("support", 0.8, 1.0, lineage_key="wire"),
            ConflictEvidence("contradict", 0.8, 1.0, lineage_key="official"),
        )
    )
    assert result.independent_lineage_count == 2
    assert result.support_weight <= 0.9
