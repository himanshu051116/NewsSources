from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

QUALITY_GATE_VERSION = "verification-quality-gate-v2"


class GateState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class QualityGateInput:
    case_count: int
    leakage_case_count: int
    macro_f1: float | None
    high_confidence_error_rate: float | None
    test_split_count: int
    selective_accuracy_80: float | None
    selective_coverage_80: float | None
    group_leakage_count: int = 0
    source_document_leakage_count: int = 0
    decision_coverage: float | None = None
    decided_accuracy: float | None = None
    unsafe_high_confidence_error_rate: float | None = None


@dataclass(frozen=True, slots=True)
class QualityGateAssessment:
    methodology_version: str
    state: GateState
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    interpretation: str


def assess_verification_quality_gate(
    metrics: QualityGateInput,
    *,
    min_cases: int = 100,
    min_test_cases: int = 30,
    min_macro_f1: float = 0.75,
    max_high_confidence_error_rate: float = 0.08,
    min_selective_accuracy_80: float = 0.85,
    min_selective_coverage_80: float = 0.35,
    min_decision_coverage: float = 0.40,
    min_decided_accuracy: float = 0.80,
    max_unsafe_high_confidence_error_rate: float = 0.10,
) -> QualityGateAssessment:
    failures: list[str] = []
    warnings: list[str] = []
    if metrics.leakage_case_count > 0:
        failures.append("benchmark identity split leakage detected")
    if metrics.group_leakage_count > 0:
        failures.append("benchmark group/event split leakage detected")
    if metrics.source_document_leakage_count > 0:
        failures.append("benchmark source-document split leakage detected")
    if metrics.case_count < min_cases:
        failures.append(f"benchmark has fewer than {min_cases} adjudicated cases")
    if metrics.test_split_count < min_test_cases:
        failures.append(f"held-out test split has fewer than {min_test_cases} cases")
    if metrics.macro_f1 is None:
        failures.append("macro F1 is unavailable")
    elif metrics.macro_f1 < min_macro_f1:
        failures.append(f"macro F1 below {min_macro_f1:.2f}")
    if metrics.high_confidence_error_rate is None:
        warnings.append("high-confidence error rate is unavailable")
    elif metrics.high_confidence_error_rate > max_high_confidence_error_rate:
        failures.append(
            f"high-confidence error rate above {max_high_confidence_error_rate:.2f}"
        )
    if metrics.selective_accuracy_80 is None:
        warnings.append("0.80 selective accuracy is unavailable")
    elif metrics.selective_accuracy_80 < min_selective_accuracy_80:
        warnings.append(f"0.80 selective accuracy below {min_selective_accuracy_80:.2f}")
    if metrics.selective_coverage_80 is None:
        warnings.append("0.80 selective coverage is unavailable")
    elif metrics.selective_coverage_80 < min_selective_coverage_80:
        warnings.append(f"0.80 selective coverage below {min_selective_coverage_80:.2f}")
    if metrics.decision_coverage is not None and metrics.decision_coverage < min_decision_coverage:
        failures.append(f"decision coverage below {min_decision_coverage:.2f}")
    if metrics.decided_accuracy is not None and metrics.decided_accuracy < min_decided_accuracy:
        failures.append(f"decided-case accuracy below {min_decided_accuracy:.2f}")
    if (
        metrics.unsafe_high_confidence_error_rate is not None
        and metrics.unsafe_high_confidence_error_rate > max_unsafe_high_confidence_error_rate
    ):
        failures.append(
            "unsafe high-confidence error rate above "
            f"{max_unsafe_high_confidence_error_rate:.2f}"
        )

    state = GateState.FAIL if failures else (GateState.WARN if warnings else GateState.PASS)
    return QualityGateAssessment(
        methodology_version=QUALITY_GATE_VERSION,
        state=state,
        failures=tuple(failures),
        warnings=tuple(warnings),
        interpretation=(
            "The release gate evaluates held-out benchmark readiness, abstention/decision coverage, "
            "and selective error behavior. Passing is evidence that the tested configuration met "
            "configured thresholds; it is not a claim of universal factual accuracy."
        ),
    )
