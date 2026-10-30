from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

SEARCH_PROMOTION_GATE_VERSION = "search-promotion-gate-v1"


class SearchPromotionState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SearchPromotionPolicy:
    min_query_count: int = 30
    min_judgment_coverage: float = 0.90
    min_relevant_query_coverage: float = 0.60
    min_ndcg_delta: float = 0.01
    min_mrr_delta: float = 0.00
    min_recall_delta: float = -0.01
    max_hybrid_p95_ms: float = 1200.0
    max_p95_regression_ms: float = 350.0
    min_semantic_coverage: float = 0.95
    min_slice_judged_queries: int = 5
    max_slice_ndcg_drop: float = 0.03
    required_languages: tuple[str, ...] = ("en", "hi")
    required_topics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchPromotionInput:
    query_count: int
    judged_query_count: int
    judgment_coverage: float | None
    relevant_query_coverage: float | None
    ndcg_delta: float | None
    mrr_delta: float | None
    recall_delta: float | None
    lexical_p95_ms: float | None
    hybrid_p95_ms: float | None
    semantic_coverage: float | None
    lexical_slices: Mapping[str, object]
    hybrid_slices: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class SearchPromotionCheck:
    key: str
    state: SearchPromotionState
    actual: object
    threshold: object
    message: str


@dataclass(frozen=True, slots=True)
class SearchPromotionAssessment:
    methodology_version: str
    state: SearchPromotionState
    checks: tuple[SearchPromotionCheck, ...]
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    interpretation: str


def assess_search_promotion(
    metrics: SearchPromotionInput,
    policy: SearchPromotionPolicy,
) -> SearchPromotionAssessment:
    checks: list[SearchPromotionCheck] = []
    failures: list[str] = []
    warnings: list[str] = []

    def check_min(key: str, actual: float | int | None, threshold: float | int, label: str) -> None:
        if actual is None:
            message = f"{label} is unavailable"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, None, threshold, message))
        elif actual < threshold:
            message = f"{label} below required threshold"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, actual, threshold, message))
        else:
            checks.append(SearchPromotionCheck(key, SearchPromotionState.PASS, actual, threshold, f"{label} meets threshold"))

    def check_max(key: str, actual: float | int | None, threshold: float | int, label: str) -> None:
        if actual is None:
            message = f"{label} is unavailable"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, None, threshold, message))
        elif actual > threshold:
            message = f"{label} exceeds allowed threshold"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, actual, threshold, message))
        else:
            checks.append(SearchPromotionCheck(key, SearchPromotionState.PASS, actual, threshold, f"{label} is within threshold"))

    check_min("query_count", metrics.query_count, policy.min_query_count, "benchmark query count")
    check_min("judgment_coverage", metrics.judgment_coverage, policy.min_judgment_coverage, "judgment coverage")
    check_min(
        "relevant_query_coverage",
        metrics.relevant_query_coverage,
        policy.min_relevant_query_coverage,
        "relevant-query coverage",
    )
    check_min("ndcg_delta", metrics.ndcg_delta, policy.min_ndcg_delta, "NDCG@10 delta")
    check_min("mrr_delta", metrics.mrr_delta, policy.min_mrr_delta, "MRR delta")
    check_min("recall_delta", metrics.recall_delta, policy.min_recall_delta, "Recall@10 delta")
    check_max("hybrid_p95_ms", metrics.hybrid_p95_ms, policy.max_hybrid_p95_ms, "hybrid p95 latency")
    latency_regression = None
    if metrics.hybrid_p95_ms is not None and metrics.lexical_p95_ms is not None:
        latency_regression = metrics.hybrid_p95_ms - metrics.lexical_p95_ms
    check_max(
        "p95_regression_ms",
        latency_regression,
        policy.max_p95_regression_ms,
        "p95 latency regression",
    )
    check_min(
        "semantic_index_coverage",
        metrics.semantic_coverage,
        policy.min_semantic_coverage,
        "semantic-index coverage",
    )

    _assess_slice_dimension(
        "language",
        policy.required_languages,
        metrics.lexical_slices,
        metrics.hybrid_slices,
        policy,
        checks,
        failures,
        warnings,
    )
    _assess_slice_dimension(
        "topic_key",
        policy.required_topics,
        metrics.lexical_slices,
        metrics.hybrid_slices,
        policy,
        checks,
        failures,
        warnings,
    )
    _assess_observed_slice_regressions(
        metrics.lexical_slices,
        metrics.hybrid_slices,
        policy,
        checks,
        failures,
    )

    state = SearchPromotionState.FAIL if failures else (SearchPromotionState.WARN if warnings else SearchPromotionState.PASS)
    return SearchPromotionAssessment(
        methodology_version=SEARCH_PROMOTION_GATE_VERSION,
        state=state,
        checks=tuple(checks),
        failures=tuple(failures),
        warnings=tuple(warnings),
        interpretation=(
            "The search promotion gate compares like-for-like labelled lexical and hybrid runs, "
            "semantic-index coverage, latency, and slice regressions. PASS means the tested configuration "
            "met the configured thresholds; it never enables production reranking automatically."
        ),
    )


def _assess_slice_dimension(
    dimension: str,
    required_values: tuple[str, ...],
    lexical_slices: Mapping[str, object],
    hybrid_slices: Mapping[str, object],
    policy: SearchPromotionPolicy,
    checks: list[SearchPromotionCheck],
    failures: list[str],
    warnings: list[str],
) -> None:
    if not required_values:
        return
    left = _dimension(lexical_slices, dimension)
    right = _dimension(hybrid_slices, dimension)
    for label in required_values:
        lex = _slice(left, label)
        hyb = _slice(right, label)
        key = f"required_slice:{dimension}:{label}"
        if lex is None or hyb is None:
            message = f"required {dimension} slice {label!r} is missing from one or both benchmark runs"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, None, "present in both runs", message))
            continue
        judged = min(_int(lex.get("judged_query_count")), _int(hyb.get("judged_query_count")))
        if judged < policy.min_slice_judged_queries:
            message = f"required {dimension} slice {label!r} has too few judged queries"
            failures.append(message)
            checks.append(
                SearchPromotionCheck(
                    key,
                    SearchPromotionState.FAIL,
                    judged,
                    policy.min_slice_judged_queries,
                    message,
                )
            )
            continue
        delta = _delta(hyb.get("ndcg@10"), lex.get("ndcg@10"))
        if delta is None:
            message = f"required {dimension} slice {label!r} lacks NDCG@10"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, None, -policy.max_slice_ndcg_drop, message))
        elif delta < -policy.max_slice_ndcg_drop:
            message = f"required {dimension} slice {label!r} regresses beyond the allowed NDCG@10 drop"
            failures.append(message)
            checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, delta, -policy.max_slice_ndcg_drop, message))
        else:
            checks.append(
                SearchPromotionCheck(
                    key,
                    SearchPromotionState.PASS,
                    delta,
                    -policy.max_slice_ndcg_drop,
                    f"required {dimension} slice {label!r} is adequately judged and within regression budget",
                )
            )


def _assess_observed_slice_regressions(
    lexical_slices: Mapping[str, object],
    hybrid_slices: Mapping[str, object],
    policy: SearchPromotionPolicy,
    checks: list[SearchPromotionCheck],
    failures: list[str],
) -> None:
    required = {
        "language": set(policy.required_languages),
        "topic_key": set(policy.required_topics),
        "result_type": set(),
    }
    for dimension in ("language", "topic_key", "result_type"):
        left = _dimension(lexical_slices, dimension)
        right = _dimension(hybrid_slices, dimension)
        for label in sorted(set(left).intersection(right)):
            if label in required[dimension]:
                continue
            lex = _slice(left, label)
            hyb = _slice(right, label)
            if lex is None or hyb is None:
                continue
            judged = min(_int(lex.get("judged_query_count")), _int(hyb.get("judged_query_count")))
            if judged < policy.min_slice_judged_queries:
                continue
            delta = _delta(hyb.get("ndcg@10"), lex.get("ndcg@10"))
            if delta is None:
                continue
            key = f"slice_regression:{dimension}:{label}"
            if delta < -policy.max_slice_ndcg_drop:
                message = f"{dimension} slice {label!r} regresses beyond the allowed NDCG@10 drop"
                failures.append(message)
                checks.append(SearchPromotionCheck(key, SearchPromotionState.FAIL, delta, -policy.max_slice_ndcg_drop, message))
            else:
                checks.append(
                    SearchPromotionCheck(
                        key,
                        SearchPromotionState.PASS,
                        delta,
                        -policy.max_slice_ndcg_drop,
                        f"{dimension} slice {label!r} stays within the NDCG@10 regression budget",
                    )
                )


def _dimension(slices: Mapping[str, object], dimension: str) -> dict[str, object]:
    value = slices.get(dimension)
    return dict(value) if isinstance(value, Mapping) else {}


def _slice(values: Mapping[str, object], label: str) -> dict[str, object] | None:
    value = values.get(label)
    return dict(value) if isinstance(value, Mapping) else None


def _int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _delta(right: object, left: object) -> float | None:
    if not isinstance(right, (int, float)) or not isinstance(left, (int, float)):
        return None
    return round(float(right) - float(left), 6)
