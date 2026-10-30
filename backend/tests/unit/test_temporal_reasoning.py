from datetime import UTC, datetime

from newsintel.domain.intelligence.temporal import (
    TemporalRelation,
    compare_temporal_contexts,
    derive_temporal_context,
)


def test_temporal_context_resolves_relative_day_against_publication_time() -> None:
    context = derive_temporal_context(
        "Officials said 12 people were affected yesterday.",
        published_at=datetime(2026, 8, 13, 12, tzinfo=UTC),
    )
    assert context.event_time == datetime(2026, 8, 12, 0, tzinfo=UTC)


def test_temporal_comparison_separates_updates_across_days() -> None:
    old = derive_temporal_context(
        "As of August 12, 2026, officials reported 12 cases.",
        published_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
    )
    new = derive_temporal_context(
        "As of August 14, 2026, officials reported 27 cases.",
        published_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
    )
    assert compare_temporal_contexts(old, new) is TemporalRelation.CLAIM_PRECEDES_EVIDENCE
