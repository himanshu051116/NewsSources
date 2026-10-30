from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

PRODUCTION_READINESS_VERSION = "production-readiness-v1"


class ReadinessState(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class ReadinessInput:
    schema_matches: bool
    quality_gate_state: str | None
    verification_manifest_coverage: float
    open_critical_review_flags: int
    open_review_flags: int
    active_authority_count: int


@dataclass(frozen=True, slots=True)
class ProductionReadinessAssessment:
    methodology_version: str
    state: ReadinessState
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: dict[str, object]
    interpretation: str


def assess_production_readiness(
    metrics: ReadinessInput,
    *,
    min_manifest_coverage: float = 0.8,
    max_open_critical_reviews: int = 0,
    require_quality_gate_pass: bool = True,
    require_active_authority: bool = True,
) -> ProductionReadinessAssessment:
    if not 0 <= min_manifest_coverage <= 1:
        raise ValueError("min_manifest_coverage must be between 0 and 1")
    if max_open_critical_reviews < 0:
        raise ValueError("max_open_critical_reviews cannot be negative")

    failures: list[str] = []
    warnings: list[str] = []
    gate = _norm(metrics.quality_gate_state)

    if not metrics.schema_matches:
        failures.append("database schema revision does not match the release")
    if require_quality_gate_pass:
        if gate != "pass":
            failures.append("latest held-out verification quality gate is not pass")
    elif gate not in {"pass", "warn"}:
        warnings.append("held-out verification quality gate is unavailable or failed")

    if metrics.verification_manifest_coverage < min_manifest_coverage:
        failures.append(
            f"verification manifest coverage below {min_manifest_coverage:.0%}"
        )
    if metrics.open_critical_review_flags > max_open_critical_reviews:
        failures.append(
            "open critical correction/retraction review flags exceed the configured limit"
        )
    if metrics.open_review_flags > metrics.open_critical_review_flags:
        warnings.append("non-critical claim review flags remain open")
    if require_active_authority and metrics.active_authority_count < 1:
        failures.append("no active approved evidence authority is configured")

    state = ReadinessState.FAIL if failures else (ReadinessState.WARN if warnings else ReadinessState.PASS)
    return ProductionReadinessAssessment(
        methodology_version=PRODUCTION_READINESS_VERSION,
        state=state,
        failures=tuple(failures),
        warnings=tuple(warnings),
        checks={
            "schema_matches": metrics.schema_matches,
            "quality_gate_state": gate or None,
            "verification_manifest_coverage": round(metrics.verification_manifest_coverage, 6),
            "open_critical_review_flags": metrics.open_critical_review_flags,
            "open_review_flags": metrics.open_review_flags,
            "active_authority_count": metrics.active_authority_count,
            "min_manifest_coverage": min_manifest_coverage,
            "max_open_critical_reviews": max_open_critical_reviews,
            "require_quality_gate_pass": require_quality_gate_pass,
            "require_active_authority": require_active_authority,
        },
        interpretation=(
            "This gate checks whether the deployed evidence pipeline is reproducible and release-ready. "
            "Passing does not claim universal factual accuracy or that all live-news conflicts are resolved."
        ),
    )


def _norm(value: str | None) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())
