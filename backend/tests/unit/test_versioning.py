from newsintel.domain.intelligence.versioning import (
    ChangeSignificance,
    VersionChangeKind,
    diff_article_versions,
)


def test_version_diff_detects_numeric_correction_and_notice() -> None:
    diff = diff_article_versions(
        old_title="Storm injures 31",
        old_text=(
            "Officials said 31 people were injured on June 5, 2026. "
            "Rescue work continued."
        ),
        new_title="Storm injures 13",
        new_text=(
            "Officials said 13 people were injured on June 5, 2026. "
            "Rescue work continued. "
            "Correction: an earlier version misstated the number injured."
        ),
    )

    kinds = [item.kind for item in diff.changes]
    assert VersionChangeKind.TITLE_CHANGED in kinds
    assert VersionChangeKind.NUMERIC_CHANGED in kinds
    assert VersionChangeKind.CORRECTION_NOTICE in kinds
    assert diff.numeric_change_count == 1
    numeric = next(item for item in diff.changes if item.kind is VersionChangeKind.NUMERIC_CHANGED)
    assert numeric.significance is ChangeSignificance.HIGH
    assert numeric.metadata is not None
    assert numeric.metadata["old_quantities"][0]["normalized_value"] == 31.0
    assert numeric.metadata["new_quantities"][0]["normalized_value"] == 13.0


def test_version_diff_detects_temporal_change_without_treating_date_as_quantity() -> None:
    diff = diff_article_versions(
        old_title="Project schedule",
        old_text="The agency said the project would open in 2027.",
        new_title="Project schedule",
        new_text="The agency said the project would open in 2028.",
    )

    assert diff.temporal_change_count == 1
    assert diff.numeric_change_count == 0
    assert any(item.kind is VersionChangeKind.TEMPORAL_CHANGED for item in diff.changes)
