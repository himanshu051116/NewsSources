from __future__ import annotations

from dataclasses import dataclass

EVENT_BENCHMARK_VERSION = "event-link-benchmark-v1"


@dataclass(frozen=True, slots=True)
class EventLinkObservation:
    expected_same_event: bool
    linked_same_event: bool
    score: float
    case_key: str | None = None
    category: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class EventLinkBenchmarkAssessment:
    benchmark_version: str
    case_count: int
    positive_count: int
    negative_count: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    accuracy: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    false_link_rate: float | None
    false_miss_rate: float | None
    mean_positive_score: float | None
    mean_negative_score: float | None
    min_positive_score: float | None
    max_negative_score: float | None
    positive_margin_to_threshold: float | None
    negative_margin_to_threshold: float | None
    failed_case_keys: tuple[str, ...]
    interpretation: str


def assess_event_link_benchmark(
    observations: tuple[EventLinkObservation, ...],
    *,
    candidate_threshold: float = 0.62,
) -> EventLinkBenchmarkAssessment:
    rows = tuple(observations)
    positives = [item for item in rows if item.expected_same_event]
    negatives = [item for item in rows if not item.expected_same_event]
    tp = sum(item.linked_same_event for item in positives)
    fn = len(positives) - tp
    fp = sum(item.linked_same_event for item in negatives)
    tn = len(negatives) - fp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else None
    )
    accuracy = (tp + tn) / len(rows) if rows else None
    false_link_rate = fp / len(negatives) if negatives else None
    false_miss_rate = fn / len(positives) if positives else None
    positive_scores = [max(0.0, min(1.0, item.score)) for item in positives]
    negative_scores = [max(0.0, min(1.0, item.score)) for item in negatives]
    min_positive = min(positive_scores) if positive_scores else None
    max_negative = max(negative_scores) if negative_scores else None
    failed = tuple(
        item.case_key or f"case:{index + 1}"
        for index, item in enumerate(rows)
        if item.expected_same_event != item.linked_same_event
    )
    return EventLinkBenchmarkAssessment(
        benchmark_version=EVENT_BENCHMARK_VERSION,
        case_count=len(rows),
        positive_count=len(positives),
        negative_count=len(negatives),
        true_positive=tp,
        true_negative=tn,
        false_positive=fp,
        false_negative=fn,
        accuracy=_round(accuracy),
        precision=_round(precision),
        recall=_round(recall),
        f1=_round(f1),
        false_link_rate=_round(false_link_rate),
        false_miss_rate=_round(false_miss_rate),
        mean_positive_score=_mean(positive_scores),
        mean_negative_score=_mean(negative_scores),
        min_positive_score=_round(min_positive),
        max_negative_score=_round(max_negative),
        positive_margin_to_threshold=(
            _round(min_positive - candidate_threshold) if min_positive is not None else None
        ),
        negative_margin_to_threshold=(
            _round(candidate_threshold - max_negative) if max_negative is not None else None
        ),
        failed_case_keys=failed,
        interpretation=(
            "Event-link benchmark metrics compare adjudicated same-event pairs with the event "
            "assignment decision. Precision measures false merging, recall measures missed links, "
            "and score margins show how close the hardest cases are to the configured candidate "
            "threshold. Results apply only to the adjudicated benchmark set."
        ),
    )


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
