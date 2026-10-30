from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Iterable

VALIDATION_PROGRAM_VERSION = "accuracy-validation-program-v1"


@dataclass(frozen=True, slots=True)
class ValidationObservation:
    case_key: str
    predicted_label: str
    adjudicated_label: str
    predicted_confidence: float
    topic_key: str | None = None
    language: str | None = None
    source_key: str | None = None
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    estimate: float | None
    lower: float | None
    upper: float | None
    sample_size: int


@dataclass(frozen=True, slots=True)
class SliceValidation:
    dimension: str
    value: str
    case_count: int
    decision_count: int
    decision_coverage: float
    decided_accuracy: float | None
    accuracy_interval: ConfidenceInterval
    unsafe_high_confidence_error_rate: float | None
    gate_state: str
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActiveSamplingTarget:
    dimension: str
    value: str
    priority: float
    reason: str
    case_count: int


@dataclass(frozen=True, slots=True)
class ValidationProgramReport:
    methodology_version: str
    corpus_fingerprint: str
    corpus_case_count: int
    decided_case_count: int
    decision_coverage: float
    decided_accuracy: float | None
    decided_accuracy_interval: ConfidenceInterval
    unsafe_high_confidence_error_rate: float | None
    overall_gate_state: str
    failures: tuple[str, ...]
    slice_results: tuple[SliceValidation, ...]
    active_sampling_targets: tuple[ActiveSamplingTarget, ...]
    interpretation: str


def build_validation_program_report(
    observations: Iterable[ValidationObservation],
    *,
    min_overall_cases: int = 30,
    min_slice_cases: int = 10,
    min_decision_coverage: float = 0.50,
    min_decided_accuracy: float = 0.80,
    max_unsafe_high_confidence_error_rate: float = 0.10,
    confidence_level_z: float = 1.959963984540054,
) -> ValidationProgramReport:
    rows = tuple(_normalized(item) for item in observations if str(item.case_key).strip())
    ordered = tuple(sorted(rows, key=lambda item: item.case_key))
    fingerprint = _corpus_fingerprint(ordered)

    decided = tuple(item for item in ordered if item.predicted_label != "not_checkable")
    correct_decisions = sum(1 for item in decided if item.predicted_label == item.adjudicated_label)
    decision_coverage = len(decided) / len(ordered) if ordered else 0.0
    decided_accuracy = correct_decisions / len(decided) if decided else None
    interval = wilson_interval(correct_decisions, len(decided), z=confidence_level_z)

    unsafe = tuple(item for item in decided if item.predicted_confidence >= 0.8)
    unsafe_errors = sum(1 for item in unsafe if item.predicted_label != item.adjudicated_label)
    unsafe_rate = unsafe_errors / len(unsafe) if unsafe else None

    failures: list[str] = []
    if len(ordered) < min_overall_cases:
        failures.append(f"benchmark_too_small:{len(ordered)}<{min_overall_cases}")
    if decision_coverage < min_decision_coverage:
        failures.append(
            f"decision_coverage_below_gate:{decision_coverage:.4f}<{min_decision_coverage:.4f}"
        )
    if decided_accuracy is None or decided_accuracy < min_decided_accuracy:
        value = "none" if decided_accuracy is None else f"{decided_accuracy:.4f}"
        failures.append(f"decided_accuracy_below_gate:{value}<{min_decided_accuracy:.4f}")
    if unsafe_rate is not None and unsafe_rate > max_unsafe_high_confidence_error_rate:
        failures.append(
            "unsafe_high_confidence_error_rate_above_gate:"
            f"{unsafe_rate:.4f}>{max_unsafe_high_confidence_error_rate:.4f}"
        )

    slice_results: list[SliceValidation] = []
    for dimension, getter in (
        ("language", lambda row: row.language),
        ("topic", lambda row: row.topic_key),
        ("source", lambda row: row.source_key),
    ):
        grouped: dict[str, list[ValidationObservation]] = {}
        for row in ordered:
            value = str(getter(row) or "unknown").strip() or "unknown"
            grouped.setdefault(value, []).append(row)
        for value, group in grouped.items():
            slice_results.append(
                _slice_validation(
                    dimension,
                    value,
                    tuple(group),
                    min_slice_cases=min_slice_cases,
                    min_decision_coverage=min_decision_coverage,
                    min_decided_accuracy=min_decided_accuracy,
                    max_unsafe_rate=max_unsafe_high_confidence_error_rate,
                    z=confidence_level_z,
                )
            )

    active = _active_sampling_targets(tuple(slice_results), min_slice_cases=min_slice_cases)
    return ValidationProgramReport(
        methodology_version=VALIDATION_PROGRAM_VERSION,
        corpus_fingerprint=fingerprint,
        corpus_case_count=len(ordered),
        decided_case_count=len(decided),
        decision_coverage=round(decision_coverage, 6),
        decided_accuracy=_round(decided_accuracy),
        decided_accuracy_interval=interval,
        unsafe_high_confidence_error_rate=_round(unsafe_rate),
        overall_gate_state="pass" if not failures else "fail",
        failures=tuple(failures),
        slice_results=tuple(sorted(slice_results, key=lambda item: (item.dimension, item.value))),
        active_sampling_targets=active,
        interpretation=(
            "The corpus fingerprint versions the adjudicated benchmark by content, not by a mutable name. "
            "Wilson intervals quantify sampling uncertainty for decided-case accuracy. Slice gates are only "
            "enforced after the configured minimum sample count; smaller slices are marked insufficient rather "
            "than falsely passing. Active-sampling targets identify underrepresented or weak slices for the next "
            "blind-review batch. Results apply only to this adjudicated corpus and do not establish universal news accuracy."
        ),
    )


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> ConfidenceInterval:
    successes = max(0, min(int(successes), int(total)))
    total = max(0, int(total))
    if total == 0:
        return ConfidenceInterval(None, None, None, 0)
    p = successes / total
    z2 = z * z
    denom = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denom
    half = z * sqrt((p * (1 - p) + z2 / (4 * total)) / total) / denom
    return ConfidenceInterval(
        estimate=round(p, 6),
        lower=round(max(0.0, center - half), 6),
        upper=round(min(1.0, center + half), 6),
        sample_size=total,
    )


def _slice_validation(
    dimension: str,
    value: str,
    rows: tuple[ValidationObservation, ...],
    *,
    min_slice_cases: int,
    min_decision_coverage: float,
    min_decided_accuracy: float,
    max_unsafe_rate: float,
    z: float,
) -> SliceValidation:
    decided = tuple(item for item in rows if item.predicted_label != "not_checkable")
    correct = sum(1 for item in decided if item.predicted_label == item.adjudicated_label)
    coverage = len(decided) / len(rows) if rows else 0.0
    accuracy = correct / len(decided) if decided else None
    unsafe = tuple(item for item in decided if item.predicted_confidence >= 0.8)
    unsafe_errors = sum(1 for item in unsafe if item.predicted_label != item.adjudicated_label)
    unsafe_rate = unsafe_errors / len(unsafe) if unsafe else None
    failures: list[str] = []
    if len(rows) < min_slice_cases:
        state = "insufficient_sample"
    else:
        if coverage < min_decision_coverage:
            failures.append("low_decision_coverage")
        if accuracy is None or accuracy < min_decided_accuracy:
            failures.append("low_decided_accuracy")
        if unsafe_rate is not None and unsafe_rate > max_unsafe_rate:
            failures.append("unsafe_high_confidence_errors")
        state = "fail" if failures else "pass"
    return SliceValidation(
        dimension=dimension,
        value=value,
        case_count=len(rows),
        decision_count=len(decided),
        decision_coverage=round(coverage, 6),
        decided_accuracy=_round(accuracy),
        accuracy_interval=wilson_interval(correct, len(decided), z=z),
        unsafe_high_confidence_error_rate=_round(unsafe_rate),
        gate_state=state,
        failures=tuple(failures),
    )


def _active_sampling_targets(
    slices: tuple[SliceValidation, ...], *, min_slice_cases: int
) -> tuple[ActiveSamplingTarget, ...]:
    targets: list[ActiveSamplingTarget] = []
    for item in slices:
        shortage = max(0, min_slice_cases - item.case_count) / max(1, min_slice_cases)
        weakness = 0.0 if item.decided_accuracy is None else max(0.0, 1.0 - item.decided_accuracy)
        uncertainty = 0.0
        if item.accuracy_interval.lower is not None and item.accuracy_interval.upper is not None:
            uncertainty = item.accuracy_interval.upper - item.accuracy_interval.lower
        priority = min(1.0, 0.50 * shortage + 0.30 * uncertainty + 0.20 * weakness)
        if item.gate_state == "fail":
            priority = min(1.0, priority + 0.20)
        if priority <= 0.05:
            continue
        reason_parts: list[str] = []
        if item.case_count < min_slice_cases:
            reason_parts.append("underrepresented")
        if uncertainty >= 0.20:
            reason_parts.append("wide_confidence_interval")
        if item.gate_state == "fail":
            reason_parts.append("quality_gate_failure")
        if not reason_parts:
            reason_parts.append("increase_precision")
        targets.append(
            ActiveSamplingTarget(
                dimension=item.dimension,
                value=item.value,
                priority=round(priority, 6),
                reason=",".join(reason_parts),
                case_count=item.case_count,
            )
        )
    return tuple(sorted(targets, key=lambda item: (-item.priority, item.dimension, item.value))[:20])


def _normalized(item: ValidationObservation) -> ValidationObservation:
    return ValidationObservation(
        case_key=str(item.case_key).strip(),
        predicted_label=_label(item.predicted_label),
        adjudicated_label=_label(item.adjudicated_label),
        predicted_confidence=_confidence(item.predicted_confidence),
        topic_key=_optional(item.topic_key),
        language=_optional(item.language),
        source_key=_optional(item.source_key),
        weight=max(0.0, float(item.weight)),
    )


def _corpus_fingerprint(rows: tuple[ValidationObservation, ...]) -> str:
    digest = sha256()
    for row in rows:
        digest.update(
            "\t".join(
                (
                    row.case_key,
                    row.adjudicated_label,
                    row.topic_key or "",
                    row.language or "",
                    row.source_key or "",
                )
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _label(value: str) -> str:
    return "_".join(str(value).strip().casefold().replace("-", "_").split())


def _confidence(value: float) -> float:
    result = float(value)
    if result > 1.0:
        result /= 100.0
    return max(0.0, min(1.0, result))


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
