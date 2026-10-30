from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable
from uuid import UUID

SEARCH_DEPLOYMENT_METHOD_VERSION = "search-deployment-control-v1"


class SearchDeploymentState(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    CANARY = "canary"
    PAUSED = "paused"


class SearchDeploymentVariant(StrEnum):
    LEXICAL = "lexical"
    HYBRID = "hybrid"
    SHADOW = "shadow"


@dataclass(frozen=True, slots=True)
class SearchCircuitBreakerPolicy:
    max_hybrid_p95_ms: float = 1500.0
    max_hybrid_error_rate: float = 0.05
    min_hybrid_samples: int = 30


@dataclass(frozen=True, slots=True)
class SearchCircuitBreakerAssessment:
    sample_count: int
    error_count: int
    error_rate: float | None
    p95_ms: float | None
    should_pause: bool
    reasons: tuple[str, ...]


def deterministic_bucket(*, subject_id: UUID | str, salt: str, bucket_count: int = 10_000) -> int:
    if bucket_count < 2:
        raise ValueError("bucket_count must be >= 2")
    material = f"{salt}:{subject_id}".encode("utf-8")
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], "big") % bucket_count


def assigned_to_canary(*, bucket: int, target_percent: float, bucket_count: int = 10_000) -> bool:
    if not 0 <= bucket < bucket_count:
        raise ValueError("bucket is outside the configured bucket range")
    if not 0.0 <= target_percent <= 100.0:
        raise ValueError("target_percent must be between 0 and 100")
    threshold = int(round((target_percent / 100.0) * bucket_count))
    return bucket < threshold


def assess_circuit_breaker(
    *,
    durations_ms: Iterable[float],
    success_flags: Iterable[bool],
    policy: SearchCircuitBreakerPolicy,
) -> SearchCircuitBreakerAssessment:
    durations = [max(0.0, float(value)) for value in durations_ms]
    successes = [bool(value) for value in success_flags]
    if len(durations) != len(successes):
        raise ValueError("durations and success_flags must have equal length")
    sample_count = len(successes)
    error_count = sum(1 for success in successes if not success)
    error_rate = (error_count / sample_count) if sample_count else None
    p95_ms = _percentile(durations, 0.95) if durations else None
    return assess_circuit_breaker_summary(
        sample_count=sample_count,
        error_count=error_count,
        p95_ms=p95_ms,
        policy=policy,
    )


def assess_circuit_breaker_summary(
    *,
    sample_count: int,
    error_count: int,
    p95_ms: float | None,
    policy: SearchCircuitBreakerPolicy,
) -> SearchCircuitBreakerAssessment:
    if sample_count < 0 or error_count < 0 or error_count > sample_count:
        raise ValueError("invalid circuit-breaker sample/error counts")
    error_rate = (error_count / sample_count) if sample_count else None
    reasons: list[str] = []
    if sample_count >= policy.min_hybrid_samples:
        if error_rate is not None and error_rate > policy.max_hybrid_error_rate:
            reasons.append("hybrid error rate exceeded the configured circuit-breaker threshold")
        if p95_ms is not None and p95_ms > policy.max_hybrid_p95_ms:
            reasons.append("hybrid p95 latency exceeded the configured circuit-breaker threshold")
    return SearchCircuitBreakerAssessment(
        sample_count=sample_count,
        error_count=error_count,
        error_rate=error_rate,
        p95_ms=p95_ms,
        should_pause=bool(reasons),
        reasons=tuple(reasons),
    )


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("at least one value is required")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight
