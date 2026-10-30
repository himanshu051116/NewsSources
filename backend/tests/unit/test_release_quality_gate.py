from newsintel.domain.intelligence.release_gates import (
    GateState,
    QualityGateInput,
    assess_verification_quality_gate,
)


def test_quality_gate_passes_healthy_held_out_benchmark():
    result = assess_verification_quality_gate(
        QualityGateInput(200, 0, 0.84, 0.04, 70, 0.91, 0.55)
    )
    assert result.state is GateState.PASS


def test_quality_gate_fails_leakage_even_when_scores_look_good():
    result = assess_verification_quality_gate(
        QualityGateInput(200, 2, 0.95, 0.01, 70, 0.98, 0.8)
    )
    assert result.state is GateState.FAIL
    assert any("leakage" in item for item in result.failures)


def test_quality_gate_fails_group_and_source_document_leakage():
    result = assess_verification_quality_gate(
        QualityGateInput(
            case_count=200,
            leakage_case_count=0,
            macro_f1=0.9,
            high_confidence_error_rate=0.02,
            test_split_count=70,
            selective_accuracy_80=0.95,
            selective_coverage_80=0.6,
            group_leakage_count=1,
            source_document_leakage_count=1,
        )
    )
    assert result.state is GateState.FAIL
    assert any("group/event" in item for item in result.failures)
    assert any("source-document" in item for item in result.failures)


def test_quality_gate_fails_when_verifier_only_looks_accurate_by_abstaining():
    result = assess_verification_quality_gate(
        QualityGateInput(
            case_count=200,
            leakage_case_count=0,
            macro_f1=0.9,
            high_confidence_error_rate=0.02,
            test_split_count=70,
            selective_accuracy_80=0.95,
            selective_coverage_80=0.6,
            decision_coverage=0.15,
            decided_accuracy=0.95,
            unsafe_high_confidence_error_rate=0.02,
        )
    )
    assert result.state is GateState.FAIL
    assert any("decision coverage" in item for item in result.failures)


def test_quality_gate_fails_unsafe_high_confidence_decisions():
    result = assess_verification_quality_gate(
        QualityGateInput(
            case_count=200,
            leakage_case_count=0,
            macro_f1=0.9,
            high_confidence_error_rate=0.02,
            test_split_count=70,
            selective_accuracy_80=0.95,
            selective_coverage_80=0.6,
            decision_coverage=0.75,
            decided_accuracy=0.9,
            unsafe_high_confidence_error_rate=0.2,
        )
    )
    assert result.state is GateState.FAIL
    assert any("unsafe high-confidence" in item for item in result.failures)
