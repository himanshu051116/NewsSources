from newsintel.domain.intelligence.outcomes import (
    CommitmentType,
    OutcomeStatus,
    assess_outcome,
    extract_trackable_commitment,
)


def test_extracts_trackable_deadline_commitment() -> None:
    item = extract_trackable_commitment(
        "The ministry said the project would be completed by 2028.",
        attribution={"speaker": "The ministry"},
    )
    assert item is not None
    assert item.commitment_type is CommitmentType.DEADLINE
    assert item.deadline_text == "2028"


def test_outcome_tracker_does_not_infer_success_from_silence() -> None:
    result = assess_outcome(
        "The ministry said the project would be completed by 2028.",
        "The ministry released a progress report this week.",
    )
    assert result.status is OutcomeStatus.PENDING


def test_outcome_tracker_detects_delay() -> None:
    result = assess_outcome(
        "The ministry said the project would be completed by 2028.",
        "The project was delayed and the opening was pushed back to 2029.",
    )
    assert result.status is OutcomeStatus.DELAYED
