from newsintel.domain.intelligence.evidence import (
    EvidencePassageRelationship,
    find_evidence_passages,
)


def test_evidence_matcher_surfaces_numeric_conflict_without_declaring_falsehood() -> None:
    passages = find_evidence_passages(
        "Officials said 31 people were injured on June 5, 2026.",
        (
            "Rescue teams worked overnight. "
            "Officials said 13 people were injured on June 5, 2026. "
            "The road reopened later."
        ),
    )

    assert passages
    assert passages[0].relationship is EvidencePassageRelationship.POTENTIAL_NUMERIC_CONFLICT
    assert passages[0].metadata["warning"].startswith("Textual matching identifies")


def test_evidence_matcher_finds_matching_assertion() -> None:
    passages = find_evidence_passages(
        "The court approved the request on June 5, 2026.",
        "The court approved the request on June 5, 2026. Lawyers welcomed the ruling.",
    )

    assert passages[0].relationship is EvidencePassageRelationship.MATCHING_ASSERTION
    assert passages[0].similarity_score == 1.0
