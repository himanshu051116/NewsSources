from newsintel.domain.intelligence.reliability import (
    ReliabilityObservation,
    assess_publisher_reliability,
    reliability_contribution,
)


def test_unsupported_claim_is_not_counted_as_publisher_failure() -> None:
    assert reliability_contribution(
        ReliabilityObservation(label="unsupported", confidence=0.9)
    ) is None


def test_supported_and_contradicted_claims_move_posterior_in_expected_direction() -> None:
    strong = assess_publisher_reliability(
        tuple(ReliabilityObservation(label="supported", confidence=0.9) for _ in range(8)),
        topic_key="numeric",
    )
    weak = assess_publisher_reliability(
        tuple(ReliabilityObservation(label="contradicted", confidence=0.9) for _ in range(8)),
        topic_key="numeric",
    )
    assert strong.posterior_mean is not None and strong.posterior_mean > 0.7
    assert weak.posterior_mean is not None and weak.posterior_mean < 0.3
    assert strong.interval_low is not None
    assert strong.interval_high is not None


def test_small_sample_is_shrunk_toward_neutral_prior() -> None:
    result = assess_publisher_reliability(
        (ReliabilityObservation(label="supported", confidence=1.0),),
        topic_key="legal",
        prior_alpha=2.0,
        prior_beta=2.0,
    )
    assert result.posterior_mean == 0.6
    assert result.effective_sample_size == 1.0


def test_disputed_claim_contributes_symmetrically() -> None:
    success, failure = reliability_contribution(
        ReliabilityObservation(label="disputed", confidence=0.8, evidence_maturity=1.0)
    ) or (0.0, 0.0)
    assert success == failure == 0.4
