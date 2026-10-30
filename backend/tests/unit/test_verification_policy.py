from newsintel.domain.intelligence.claims import ClaimVerificationLabel
from newsintel.domain.intelligence.verification import (
    EvidenceStance,
    VerificationEvidence,
    verify_from_evidence,
)


def test_primary_support_can_support_claim() -> None:
    decision = verify_from_evidence(
        (
            VerificationEvidence(
                stance=EvidenceStance.SUPPORT,
                independence_score=0.9,
                evidence_quality=0.95,
                primary_source=True,
                lineage_key="official-record",
            ),
        )
    )

    assert decision.label is ClaimVerificationLabel.SUPPORTED
    assert decision.confidence_score is not None


def test_syndicated_copies_are_not_double_counted() -> None:
    decision = verify_from_evidence(
        (
            VerificationEvidence(
                stance=EvidenceStance.SUPPORT,
                independence_score=0.8,
                lineage_key="wire:123",
            ),
            VerificationEvidence(
                stance=EvidenceStance.SUPPORT,
                independence_score=0.8,
                lineage_key="wire:123",
            ),
        )
    )

    assert decision.label is ClaimVerificationLabel.NOT_CHECKABLE
    assert decision.reasoning_trace["lineages_after_deduplication"] == 1


def test_absence_of_evidence_is_not_contradiction() -> None:
    incomplete = verify_from_evidence(())
    complete = verify_from_evidence((), retrieval_complete=True)

    assert incomplete.label is ClaimVerificationLabel.NOT_CHECKABLE
    assert complete.label is ClaimVerificationLabel.UNSUPPORTED


def test_primary_contradiction_has_priority() -> None:
    decision = verify_from_evidence(
        (
            VerificationEvidence(
                stance=EvidenceStance.SUPPORT,
                independence_score=0.7,
                lineage_key="news-a",
            ),
            VerificationEvidence(
                stance=EvidenceStance.CONTRADICT,
                independence_score=0.95,
                primary_source=True,
                lineage_key="primary-record",
            ),
        )
    )

    assert decision.label is ClaimVerificationLabel.CONTRADICTED
