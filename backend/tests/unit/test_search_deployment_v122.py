from __future__ import annotations

from pathlib import Path
from uuid import UUID

from newsintel import __version__
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION, REQUIRED_V22_INDEXES, REQUIRED_V22_TABLES
from newsintel.domain.search.deployment import (
    SearchCircuitBreakerPolicy,
    assess_circuit_breaker,
    assigned_to_canary,
    deterministic_bucket,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "newsintel"
ROUTES = SRC / "api" / "routes"


def test_v122_release_contract_and_schema_objects() -> None:
    assert __version__ == "1.25.0"
    assert EXPECTED_SCHEMA_REVISION == "0034_article_revision_history"
    assert {
        "search_deployments",
        "search_deployment_observations",
        "search_deployment_outcomes",
        "search_deployment_actions",
    }.issubset(REQUIRED_V22_TABLES)
    assert {
        "ix_search_deployments_state_updated",
        "ix_search_deployment_obs_deployment_created",
        "ix_search_deployment_obs_variant_created",
        "ix_search_deployment_outcomes_observation_created",
        "ix_search_deployment_actions_deployment_created",
    }.issubset(REQUIRED_V22_INDEXES)


def test_deterministic_bucketing_is_stable_and_exposure_bounded() -> None:
    subject = UUID("018f6f0f-1111-7777-8888-123456789abc")
    first = deterministic_bucket(subject_id=subject, salt="rollout-a")
    second = deterministic_bucket(subject_id=subject, salt="rollout-a")
    other = deterministic_bucket(subject_id=subject, salt="rollout-b")
    assert first == second
    assert 0 <= first < 10_000
    assert 0 <= other < 10_000
    assert assigned_to_canary(bucket=0, target_percent=0.1)
    assert not assigned_to_canary(bucket=9_999, target_percent=99.0)
    assert not assigned_to_canary(bucket=first, target_percent=0.0)
    assert assigned_to_canary(bucket=first, target_percent=100.0)


def test_circuit_breaker_requires_minimum_samples_then_pauses_on_latency_or_errors() -> None:
    policy = SearchCircuitBreakerPolicy(max_hybrid_p95_ms=500.0, max_hybrid_error_rate=0.10, min_hybrid_samples=5)
    small = assess_circuit_breaker(
        durations_ms=[900.0, 900.0], success_flags=[False, False], policy=policy
    )
    assert not small.should_pause
    latency = assess_circuit_breaker(
        durations_ms=[100.0, 120.0, 150.0, 800.0, 900.0],
        success_flags=[True] * 5,
        policy=policy,
    )
    assert latency.should_pause
    assert any("p95 latency" in reason for reason in latency.reasons)
    errors = assess_circuit_breaker(
        durations_ms=[100.0] * 10,
        success_flags=[True] * 8 + [False] * 2,
        policy=policy,
    )
    assert errors.should_pause
    assert any("error rate" in reason for reason in errors.reasons)


def test_deployment_service_is_approval_gated_article_only_and_auto_pauses() -> None:
    source = (SRC / "application" / "search" / "deployment_service.py").read_text(encoding="utf-8")
    assert "approve_candidate" in source
    assert 'evaluation.state != "pass"' in source
    assert 'result_type != "article"' in source
    assert 'action="auto_pause"' in source
    assert 'deployment.state = SearchDeploymentState.PAUSED.value' in source
    assert "semantic_reranker_unavailable" in source
    assert "shadow_evaluation_served_lexical" in source


def test_production_reranker_preserves_lexical_pagination_only_when_requested() -> None:
    source = (SRC / "application" / "search" / "rerank_service.py").read_text(encoding="utf-8")
    assert "preserve_cursor: bool = False" in source
    assert 'lexical.next_cursor if preserve_cursor else None' in source
    assert 'mode_label="hybrid_article_rerank_canary_v1"' in (SRC / "application" / "search" / "deployment_service.py").read_text(encoding="utf-8")


def test_v122_api_and_ui_expose_control_without_defaulting_to_canary() -> None:
    routes = (ROUTES / "search_deployment.py").read_text(encoding="utf-8")
    quality_ui = (ROUTES / "search_quality_dashboard.py").read_text(encoding="utf-8")
    search_ui = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    assert '"/search/deployment"' in routes
    assert '"/search/deployment/outcome"' in routes
    assert "Production deployment control" in quality_ui
    assert "OFF by default" in quality_ui
    assert "Auto-pause on circuit breach" in quality_ui
    assert "deployment-result-link" in search_ui
    assert "hybrid_canary" in search_ui


def test_v122_migration_adds_telemetry_and_audit_without_seeding_exposure() -> None:
    source = (ROOT / "migrations" / "versions" / "0031_search_deployment_control.py").read_text(encoding="utf-8")
    assert 'revision: str = "0031_search_deployment_control"' in source
    assert 'down_revision: str | None = "0030_search_promotion_gates"' in source
    assert '"search_deployments"' in source
    assert '"search_deployment_observations"' in source
    assert '"search_deployment_outcomes"' in source
    assert '"search_deployment_actions"' in source
    assert "INSERT INTO search_deployments" not in source
