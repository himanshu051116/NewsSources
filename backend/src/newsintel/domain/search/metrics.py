from __future__ import annotations

from math import log2
from statistics import mean
from typing import Iterable, Mapping, Sequence


ResultKey = tuple[str, str]


def precision_at_k(ranked: Sequence[ResultKey], grades: Mapping[ResultKey, int], k: int) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    top = ranked[:k]
    if not top:
        return 0.0
    relevant = sum(1 for key in top if int(grades.get(key, 0)) > 0)
    return relevant / k


def recall_at_k(ranked: Sequence[ResultKey], grades: Mapping[ResultKey, int], k: int) -> float | None:
    if k <= 0:
        raise ValueError("k must be positive")
    relevant_total = sum(1 for grade in grades.values() if int(grade) > 0)
    if relevant_total == 0:
        return None
    relevant_found = sum(1 for key in ranked[:k] if int(grades.get(key, 0)) > 0)
    return relevant_found / relevant_total


def reciprocal_rank(ranked: Sequence[ResultKey], grades: Mapping[ResultKey, int]) -> float:
    for index, key in enumerate(ranked, start=1):
        if int(grades.get(key, 0)) > 0:
            return 1.0 / index
    return 0.0


def ndcg_at_k(ranked: Sequence[ResultKey], grades: Mapping[ResultKey, int], k: int) -> float | None:
    if k <= 0:
        raise ValueError("k must be positive")
    ideal_grades = sorted((max(0, int(v)) for v in grades.values()), reverse=True)[:k]
    ideal = _dcg(ideal_grades)
    if ideal <= 0.0:
        return None
    observed = [max(0, int(grades.get(key, 0))) for key in ranked[:k]]
    return _dcg(observed) / ideal


def aggregate_query_metrics(per_query: Iterable[dict[str, float | None]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for item in per_query:
        for key, value in item.items():
            if value is None:
                continue
            buckets.setdefault(key, []).append(float(value))
    return {key: round(mean(values), 6) for key, values in buckets.items() if values}


def _dcg(grades: Sequence[int]) -> float:
    total = 0.0
    for index, grade in enumerate(grades, start=1):
        gain = (2 ** max(0, int(grade))) - 1
        if gain:
            total += gain / log2(index + 1)
    return total
