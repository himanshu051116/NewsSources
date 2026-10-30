from datetime import UTC, datetime

from newsintel.domain.intelligence.stance import PassageStance, assess_evidence_stance


def test_same_time_numeric_mismatch_is_contradictory_candidate() -> None:
    result = assess_evidence_stance(
        "Officials reported 31 people were injured on August 12, 2026.",
        "The official bulletin reported 13 people were injured on August 12, 2026.",
        claim_published_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        evidence_published_at=datetime(2026, 8, 12, 13, tzinfo=UTC),
    )
    assert result.stance is PassageStance.CONTRADICT


def test_different_as_of_dates_turn_numeric_difference_into_update() -> None:
    result = assess_evidence_stance(
        "As of August 12, 2026, officials reported 12 people were affected.",
        "As of August 14, 2026, officials reported 27 people were affected.",
        claim_published_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        evidence_published_at=datetime(2026, 8, 14, 12, tzinfo=UTC),
    )
    assert result.stance is PassageStance.TEMPORAL_UPDATE


def test_matching_passage_supports_without_claiming_truth() -> None:
    result = assess_evidence_stance(
        "The agency reported revenue rose 18% in 2026.",
        "In its filing, the agency reported revenue rose 18% in 2026.",
    )
    assert result.stance is PassageStance.SUPPORT
    assert result.confidence < 1.0
