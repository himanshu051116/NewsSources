from __future__ import annotations

from dataclasses import dataclass

CALIBRATION_METHODOLOGY_VERSION = "verification-confidence-calibration-v2"


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    predicted_confidence: float
    outcome_correct: bool
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    weight: float
    mean_confidence: float | None
    empirical_accuracy: float | None
    calibration_gap: float | None


@dataclass(frozen=True, slots=True)
class CalibrationAssessment:
    methodology_version: str
    observation_count: int
    effective_weight: float
    brier_score: float | None
    expected_calibration_error: float | None
    mean_confidence: float | None
    empirical_accuracy: float | None
    bins: tuple[CalibrationBin, ...]
    interpretation: str


def assess_confidence_calibration(
    observations: tuple[CalibrationObservation, ...],
    *,
    bin_count: int = 10,
) -> CalibrationAssessment:
    if bin_count < 2 or bin_count > 50:
        raise ValueError("bin_count must be between 2 and 50")
    prepared: list[tuple[float, float, float]] = []
    for item in observations:
        confidence = _normalize(item.predicted_confidence)
        weight = max(0.0, float(item.weight))
        if weight == 0.0:
            continue
        outcome = 1.0 if item.outcome_correct else 0.0
        prepared.append((confidence, outcome, weight))
    total_weight = sum(item[2] for item in prepared)
    if not prepared or total_weight <= 0:
        return CalibrationAssessment(
            methodology_version=CALIBRATION_METHODOLOGY_VERSION,
            observation_count=len(observations),
            effective_weight=0.0,
            brier_score=None,
            expected_calibration_error=None,
            mean_confidence=None,
            empirical_accuracy=None,
            bins=tuple(_empty_bins(bin_count)),
            interpretation="No weighted adjudicated outcomes were available for confidence calibration.",
        )

    bins: list[CalibrationBin] = []
    ece = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        rows = [
            row for row in prepared
            if (lower <= row[0] < upper) or (index == bin_count - 1 and row[0] == 1.0)
        ]
        bin_weight = sum(row[2] for row in rows)
        if not rows or bin_weight == 0:
            bins.append(CalibrationBin(lower, upper, 0, 0.0, None, None, None))
            continue
        mean_confidence = sum(row[0] * row[2] for row in rows) / bin_weight
        accuracy = sum(row[1] * row[2] for row in rows) / bin_weight
        gap = abs(mean_confidence - accuracy)
        ece += gap * (bin_weight / total_weight)
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=len(rows),
                weight=round(bin_weight, 6),
                mean_confidence=round(mean_confidence, 6),
                empirical_accuracy=round(accuracy, 6),
                calibration_gap=round(gap, 6),
            )
        )

    brier = sum(((confidence - outcome) ** 2) * weight for confidence, outcome, weight in prepared) / total_weight
    mean_confidence = sum(confidence * weight for confidence, _, weight in prepared) / total_weight
    accuracy = sum(outcome * weight for _, outcome, weight in prepared) / total_weight
    return CalibrationAssessment(
        methodology_version=CALIBRATION_METHODOLOGY_VERSION,
        observation_count=len(prepared),
        effective_weight=round(total_weight, 6),
        brier_score=round(brier, 6),
        expected_calibration_error=round(ece, 6),
        mean_confidence=round(mean_confidence, 6),
        empirical_accuracy=round(accuracy, 6),
        bins=tuple(bins),
        interpretation=(
            "Calibration compares stated confidence for substantive verification verdicts with later "
            "adjudicated outcomes. Abstention coverage is evaluated separately by the benchmark layer. "
            "It evaluates the confidence model, not publisher ideology or article popularity."
        ),
    )


def _normalize(value: float) -> float:
    result = float(value)
    if result > 1.0:
        result /= 100.0
    return min(1.0, max(0.0, result))


def _empty_bins(count: int) -> list[CalibrationBin]:
    return [
        CalibrationBin(index / count, (index + 1) / count, 0, 0.0, None, None, None)
        for index in range(count)
    ]
