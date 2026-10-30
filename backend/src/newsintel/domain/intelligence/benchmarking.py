from __future__ import annotations

from dataclasses import dataclass

BENCHMARK_METHODOLOGY_VERSION = "verification-benchmark-v3"
ABSTENTION_LABELS = frozenset({"not_checkable"})


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    predicted_label: str
    predicted_confidence: float
    adjudicated_label: str
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class LabelMetrics:
    label: str
    support: float
    precision: float | None
    recall: float | None
    f1: float | None


@dataclass(frozen=True, slots=True)
class SelectiveMetrics:
    threshold: float
    coverage: float
    accuracy: float | None
    error_rate: float | None
    selected_weight: float


@dataclass(frozen=True, slots=True)
class BenchmarkAssessment:
    methodology_version: str
    observation_count: int
    effective_weight: float
    accuracy: float | None
    macro_precision: float | None
    macro_recall: float | None
    macro_f1: float | None
    high_confidence_error_rate: float | None
    decision_weight: float
    decision_coverage: float
    abstention_rate: float
    decided_accuracy: float | None
    decided_macro_f1: float | None
    unsafe_high_confidence_error_rate: float | None
    per_label: tuple[LabelMetrics, ...]
    confusion_matrix: dict[str, dict[str, float]]
    selective_metrics: tuple[SelectiveMetrics, ...]
    interpretation: str


def assess_verification_benchmark(
    observations: tuple[BenchmarkObservation, ...],
    *,
    thresholds: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95),
) -> BenchmarkAssessment:
    prepared: list[tuple[str, str, float, float]] = []
    for item in observations:
        weight = max(0.0, float(item.weight))
        if weight <= 0:
            continue
        predicted = _label(item.predicted_label)
        adjudicated = _label(item.adjudicated_label)
        if not predicted or not adjudicated:
            continue
        prepared.append((predicted, adjudicated, _confidence(item.predicted_confidence), weight))

    total_weight = sum(row[3] for row in prepared)
    if total_weight <= 0:
        return BenchmarkAssessment(
            methodology_version=BENCHMARK_METHODOLOGY_VERSION,
            observation_count=0,
            effective_weight=0.0,
            accuracy=None,
            macro_precision=None,
            macro_recall=None,
            macro_f1=None,
            high_confidence_error_rate=None,
            decision_weight=0.0,
            decision_coverage=0.0,
            abstention_rate=0.0,
            decided_accuracy=None,
            decided_macro_f1=None,
            unsafe_high_confidence_error_rate=None,
            per_label=(),
            confusion_matrix={},
            selective_metrics=tuple(
                SelectiveMetrics(float(t), 0.0, None, None, 0.0)
                for t in _thresholds(thresholds)
            ),
            interpretation="No weighted adjudicated benchmark cases were available.",
        )

    overall = _classification(prepared)
    selective = tuple(_selective(prepared, total_weight, threshold) for threshold in _thresholds(thresholds))

    high_confidence = [row for row in prepared if row[2] >= 0.9]
    high_weight = sum(row[3] for row in high_confidence)
    high_error = (
        sum(row[3] for row in high_confidence if row[0] != row[1]) / high_weight
        if high_weight > 0
        else None
    )

    decided = [row for row in prepared if row[0] not in ABSTENTION_LABELS]
    decision_weight = sum(row[3] for row in decided)
    decision_coverage = decision_weight / total_weight if total_weight > 0 else 0.0
    decided_metrics = _classification(decided) if decision_weight > 0 else None

    unsafe_high = [row for row in decided if row[2] >= 0.8]
    unsafe_high_weight = sum(row[3] for row in unsafe_high)
    unsafe_high_error = (
        sum(row[3] for row in unsafe_high if row[0] != row[1]) / unsafe_high_weight
        if unsafe_high_weight > 0
        else None
    )

    return BenchmarkAssessment(
        methodology_version=BENCHMARK_METHODOLOGY_VERSION,
        observation_count=len(prepared),
        effective_weight=round(total_weight, 6),
        accuracy=overall["accuracy"],
        macro_precision=overall["macro_precision"],
        macro_recall=overall["macro_recall"],
        macro_f1=overall["macro_f1"],
        high_confidence_error_rate=_round(high_error),
        decision_weight=round(decision_weight, 6),
        decision_coverage=round(decision_coverage, 6),
        abstention_rate=round(1.0 - decision_coverage, 6),
        decided_accuracy=(decided_metrics or {}).get("accuracy"),
        decided_macro_f1=(decided_metrics or {}).get("macro_f1"),
        unsafe_high_confidence_error_rate=_round(unsafe_high_error),
        per_label=overall["per_label"],
        confusion_matrix=overall["confusion_matrix"],
        selective_metrics=selective,
        interpretation=(
            "Benchmark metrics compare stored verification predictions with externally adjudicated "
            "labels. All-case metrics count abstentions as ordinary predictions; decision metrics "
            "separately report accuracy and macro F1 only when the system rendered a substantive "
            "verdict, while decision coverage/abstention rate show how often it withheld judgment. "
            "Selective metrics show the accuracy/coverage trade-off at confidence thresholds. None "
            "of these metrics establish ground truth without independent, representative adjudication."
        ),
    )


def _classification(rows: list[tuple[str, str, float, float]]) -> dict[str, object]:
    total_weight = sum(row[3] for row in rows)
    if total_weight <= 0:
        return {
            "accuracy": None,
            "macro_precision": None,
            "macro_recall": None,
            "macro_f1": None,
            "per_label": (),
            "confusion_matrix": {},
        }

    labels = sorted({row[0] for row in rows} | {row[1] for row in rows})
    confusion: dict[str, dict[str, float]] = {
        truth: {prediction: 0.0 for prediction in labels} for truth in labels
    }
    correct_weight = 0.0
    for predicted, adjudicated, _, weight in rows:
        confusion[adjudicated][predicted] += weight
        if predicted == adjudicated:
            correct_weight += weight

    label_metrics: list[LabelMetrics] = []
    precision_values: list[float] = []
    recall_values: list[float] = []
    f1_values: list[float] = []
    for label in labels:
        tp = confusion[label][label]
        predicted_positive = sum(confusion[truth][label] for truth in labels)
        actual_positive = sum(confusion[label].values())
        precision = tp / predicted_positive if predicted_positive > 0 else None
        recall = tp / actual_positive if actual_positive > 0 else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall > 0
            else None
        )
        if precision is not None:
            precision_values.append(precision)
        if recall is not None:
            recall_values.append(recall)
        if f1 is not None:
            f1_values.append(f1)
        label_metrics.append(
            LabelMetrics(
                label=label,
                support=round(actual_positive, 6),
                precision=_round(precision),
                recall=_round(recall),
                f1=_round(f1),
            )
        )

    return {
        "accuracy": round(correct_weight / total_weight, 6),
        "macro_precision": _mean(precision_values),
        "macro_recall": _mean(recall_values),
        "macro_f1": _mean(f1_values),
        "per_label": tuple(label_metrics),
        "confusion_matrix": {
            truth: {prediction: round(value, 6) for prediction, value in row.items()}
            for truth, row in confusion.items()
        },
    }


def _selective(
    rows: list[tuple[str, str, float, float]],
    total_weight: float,
    threshold: float,
) -> SelectiveMetrics:
    selected = [row for row in rows if row[2] >= threshold and row[0] not in ABSTENTION_LABELS]
    selected_weight = sum(row[3] for row in selected)
    if selected_weight <= 0:
        return SelectiveMetrics(round(threshold, 4), 0.0, None, None, 0.0)
    correct = sum(row[3] for row in selected if row[0] == row[1])
    accuracy = correct / selected_weight
    return SelectiveMetrics(
        threshold=round(threshold, 4),
        coverage=round(selected_weight / total_weight, 6),
        accuracy=round(accuracy, 6),
        error_rate=round(1.0 - accuracy, 6),
        selected_weight=round(selected_weight, 6),
    )


def _thresholds(values: tuple[float, ...]) -> tuple[float, ...]:
    normalized = sorted({_confidence(value) for value in values})
    return tuple(normalized)


def _confidence(value: float) -> float:
    result = float(value)
    if result > 1.0:
        result /= 100.0
    return max(0.0, min(1.0, result))


def _label(value: str) -> str:
    return "_".join(str(value).strip().casefold().replace("-", "_").split())


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
