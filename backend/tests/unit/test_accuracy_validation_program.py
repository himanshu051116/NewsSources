from newsintel.domain.intelligence.validation_program import (
    ValidationObservation,
    build_validation_program_report,
    wilson_interval,
)


def _case(i: int, predicted: str, truth: str, *, language: str = "en", topic: str = "policy", source: str = "a") -> ValidationObservation:
    return ValidationObservation(
        case_key=f"case-{i}",
        predicted_label=predicted,
        adjudicated_label=truth,
        predicted_confidence=0.9,
        language=language,
        topic_key=topic,
        source_key=source,
    )


def test_wilson_interval_is_bounded_and_not_overconfident_for_small_samples() -> None:
    interval = wilson_interval(5, 5)
    assert interval.estimate == 1.0
    assert 0.5 < interval.lower < 1.0
    assert interval.upper == 1.0


def test_validation_program_versions_corpus_independent_of_input_order() -> None:
    rows = (
        _case(1, "supported", "supported"),
        _case(2, "contradicted", "contradicted"),
    )
    left = build_validation_program_report(rows, min_overall_cases=1, min_slice_cases=1)
    right = build_validation_program_report(tuple(reversed(rows)), min_overall_cases=1, min_slice_cases=1)
    assert left.corpus_fingerprint == right.corpus_fingerprint


def test_slice_gates_distinguish_failure_from_insufficient_sample() -> None:
    rows = tuple(
        [_case(i, "supported", "supported", language="en") for i in range(1, 11)]
        + [_case(20, "supported", "contradicted", language="hi")]
    )
    result = build_validation_program_report(rows, min_overall_cases=1, min_slice_cases=5)
    by_key = {(item.dimension, item.value): item for item in result.slice_results}
    assert by_key[("language", "en")].gate_state == "pass"
    assert by_key[("language", "hi")].gate_state == "insufficient_sample"
    assert any(item.dimension == "language" and item.value == "hi" for item in result.active_sampling_targets)


def test_overall_gate_penalizes_low_coverage_and_unsafe_errors() -> None:
    rows = tuple(
        [_case(i, "not_checkable", "supported") for i in range(1, 7)]
        + [_case(i, "supported", "contradicted") for i in range(7, 11)]
    )
    result = build_validation_program_report(rows, min_overall_cases=5, min_slice_cases=2)
    assert result.overall_gate_state == "fail"
    assert result.decision_coverage == 0.4
    assert result.unsafe_high_confidence_error_rate == 1.0
    assert any(item.startswith("decision_coverage_below_gate") for item in result.failures)
