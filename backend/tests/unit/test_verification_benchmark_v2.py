from newsintel.domain.intelligence.benchmarking import (
    BenchmarkObservation,
    assess_verification_benchmark,
)


def test_benchmark_reports_multiclass_and_selective_metrics() -> None:
    result = assess_verification_benchmark(
        (
            BenchmarkObservation("supported", 0.95, "supported"),
            BenchmarkObservation("supported", 0.92, "contradicted"),
            BenchmarkObservation("contradicted", 0.75, "contradicted"),
            BenchmarkObservation("disputed", 0.55, "disputed"),
        )
    )
    assert result.observation_count == 4
    assert result.accuracy == 0.75
    assert result.macro_f1 is not None
    assert result.high_confidence_error_rate == 0.5
    threshold_09 = next(item for item in result.selective_metrics if item.threshold == 0.9)
    assert threshold_09.coverage == 0.5
    assert threshold_09.accuracy == 0.5
    assert result.confusion_matrix["contradicted"]["supported"] == 1.0


def test_benchmark_ignores_zero_weight_cases() -> None:
    result = assess_verification_benchmark(
        (
            BenchmarkObservation("supported", 0.99, "contradicted", weight=0.0),
            BenchmarkObservation("supported", 0.8, "supported", weight=2.0),
        )
    )
    assert result.observation_count == 1
    assert result.effective_weight == 2.0
    assert result.accuracy == 1.0
