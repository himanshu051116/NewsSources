from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from newsintel.domain.intelligence.claims import ClaimVerificationLabel

RELIABILITY_METHODOLOGY_VERSION = "publisher-topic-bayesian-reliability-v1"


class ReliabilitySignalDisposition(StrEnum):
    SUPPORT = "support"
    FAILURE = "failure"
    MIXED = "mixed"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class ReliabilityObservation:
    label: str
    confidence: float | None
    claim_type: str | None = None
    evidence_maturity: float = 1.0


@dataclass(frozen=True, slots=True)
class ReliabilityAssessment:
    methodology_version: str
    topic_key: str
    posterior_mean: float | None
    interval_low: float | None
    interval_high: float | None
    effective_successes: float
    effective_failures: float
    effective_sample_size: float
    raw_observation_count: int
    excluded_observation_count: int
    prior_alpha: float
    prior_beta: float
    interpretation: str


def assess_publisher_reliability(
    observations: tuple[ReliabilityObservation, ...],
    *,
    topic_key: str = "all",
    prior_alpha: float = 2.0,
    prior_beta: float = 2.0,
) -> ReliabilityAssessment:
    """Estimate evidence-grounded publisher reliability with Bayesian shrinkage.

    Only mature supported/contradicted/disputed/misleading claim assessments contribute.
    ``unsupported`` is excluded because failure to find evidence is not proof that the
    publisher's claim was false. Small samples stay close to the neutral prior.
    """

    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("reliability priors must be positive")
    successes = 0.0
    failures = 0.0
    excluded = 0
    used = 0
    for observation in observations:
        contribution = reliability_contribution(observation)
        if contribution is None:
            excluded += 1
            continue
        success, failure = contribution
        successes += success
        failures += failure
        used += 1

    alpha = prior_alpha + successes
    beta = prior_beta + failures
    effective_n = successes + failures
    if used == 0:
        mean: float | None = None
        low: float | None = None
        high: float | None = None
    else:
        mean = alpha / (alpha + beta)
        # Normal approximation to the Beta posterior. The interval is explicitly marked
        # approximate; it avoids adding a heavyweight statistics dependency.
        variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
        half_width = 1.96 * math.sqrt(max(0.0, variance))
        low = max(0.0, mean - half_width)
        high = min(1.0, mean + half_width)

    return ReliabilityAssessment(
        methodology_version=RELIABILITY_METHODOLOGY_VERSION,
        topic_key=topic_key,
        posterior_mean=_rounded(mean),
        interval_low=_rounded(low),
        interval_high=_rounded(high),
        effective_successes=round(successes, 4),
        effective_failures=round(failures, 4),
        effective_sample_size=round(effective_n, 4),
        raw_observation_count=len(observations),
        excluded_observation_count=excluded,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        interpretation=(
            "Evidence-grounded historical estimate with Bayesian shrinkage. It is scoped "
            "to the selected subject topic and time window, and is not a permanent label for "
            "the publisher. Unsupported/not-checkable claims are not counted as failures."
        ),
    )


def reliability_contribution(
    observation: ReliabilityObservation,
) -> tuple[float, float] | None:
    label = observation.label.strip().casefold()
    confidence = _normalize_confidence(observation.confidence)
    maturity = min(1.0, max(0.0, float(observation.evidence_maturity)))
    weight = confidence * maturity
    if weight < 0.25:
        return None
    if label == ClaimVerificationLabel.SUPPORTED.value:
        return weight, 0.0
    if label == ClaimVerificationLabel.CONTRADICTED.value:
        return 0.0, weight
    if label == ClaimVerificationLabel.MISLEADING.value:
        # Misleading is treated as primarily adverse but not identical to a direct factual
        # contradiction because the underlying statement may contain partially correct facts.
        return 0.2 * weight, 0.8 * weight
    if label == ClaimVerificationLabel.DISPUTED.value:
        return 0.5 * weight, 0.5 * weight
    # Unsupported and not-checkable are deliberately excluded.
    return None


def _normalize_confidence(value: float | None) -> float:
    if value is None:
        return 0.5
    normalized = float(value)
    if normalized > 1.0:
        normalized /= 100.0
    return min(1.0, max(0.0, normalized))


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
