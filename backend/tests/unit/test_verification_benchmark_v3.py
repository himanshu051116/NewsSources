from newsintel.domain.intelligence.benchmarking import BenchmarkObservation, assess_verification_benchmark


def test_benchmark_separates_abstention_from_wrong_decision() -> None:
    result = assess_verification_benchmark(
        (
            BenchmarkObservation("supported", 0.93, "supported"),
            BenchmarkObservation("not_checkable", 0.0, "contradicted"),
            BenchmarkObservation("contradicted", 0.91, "supported"),
            BenchmarkObservation("not_checkable", 0.0, "supported"),
        )
    )
    assert result.observation_count == 4
    assert result.decision_coverage == 0.5
    assert result.abstention_rate == 0.5
    assert result.decided_accuracy == 0.5
    assert result.unsafe_high_confidence_error_rate == 0.5
    assert result.accuracy == 0.25


def test_selective_metrics_do_not_treat_abstention_as_selected_prediction() -> None:
    result = assess_verification_benchmark(
        (
            BenchmarkObservation("not_checkable", 0.99, "supported"),
            BenchmarkObservation("supported", 0.9, "supported"),
        )
    )
    threshold = next(item for item in result.selective_metrics if item.threshold == 0.9)
    assert threshold.selected_weight == 1.0
    assert threshold.coverage == 0.5
    assert threshold.accuracy == 1.0
