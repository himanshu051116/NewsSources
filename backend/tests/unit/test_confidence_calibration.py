import pytest

from newsintel.domain.intelligence.calibration import (
    CalibrationObservation,
    assess_confidence_calibration,
)


def test_perfectly_calibrated_extreme_predictions_have_zero_brier() -> None:
    result = assess_confidence_calibration(
        (
            CalibrationObservation(1.0, True),
            CalibrationObservation(0.0, False),
        ),
        bin_count=5,
    )
    assert result.brier_score == 0.0
    assert result.empirical_accuracy == 0.5
    assert result.mean_confidence == 0.5


def test_overconfident_wrong_predictions_are_penalized() -> None:
    result = assess_confidence_calibration(
        (
            CalibrationObservation(0.95, False),
            CalibrationObservation(0.90, False),
        ),
        bin_count=10,
    )
    assert result.brier_score is not None and result.brier_score > 0.8
    assert result.expected_calibration_error is not None and result.expected_calibration_error > 0.8


def test_invalid_bin_count_rejected() -> None:
    with pytest.raises(ValueError):
        assess_confidence_calibration((), bin_count=1)
