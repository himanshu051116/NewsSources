from __future__ import annotations

from pathlib import Path

from newsintel import __version__
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION, REQUIRED_V21_INDEXES, REQUIRED_V21_TABLES
from newsintel.domain.search.promotion import (
    SearchPromotionInput,
    SearchPromotionPolicy,
    SearchPromotionState,
    assess_search_promotion,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "newsintel"
ROUTES = SRC / "api" / "routes"


def _input(**overrides):
    base = dict(
        query_count=50,
        judged_query_count=48,
        judgment_coverage=0.96,
        relevant_query_coverage=0.80,
        ndcg_delta=0.03,
        mrr_delta=0.02,
        recall_delta=0.0,
        lexical_p95_ms=220.0,
        hybrid_p95_ms=410.0,
        semantic_coverage=0.98,
        lexical_slices={
            "language": {
                "en": {"judged_query_count": 20, "ndcg@10": 0.80},
                "hi": {"judged_query_count": 12, "ndcg@10": 0.70},
            }
        },
        hybrid_slices={
            "language": {
                "en": {"judged_query_count": 20, "ndcg@10": 0.84},
                "hi": {"judged_query_count": 12, "ndcg@10": 0.72},
            }
        },
    )
    base.update(overrides)
    return SearchPromotionInput(**base)


def test_v121_release_contract_and_schema_objects() -> None:
    assert __version__ == "1.25.0"
    assert EXPECTED_SCHEMA_REVISION == "0034_article_revision_history"
    assert {"search_promotion_policies", "search_promotion_evaluations", "search_promotion_decisions"}.issubset(REQUIRED_V21_TABLES)
    assert {
        "ix_search_promotion_policies_updated",
        "ix_search_promotion_evaluations_set_created",
        "ix_search_promotion_evaluations_policy_created",
        "ix_search_promotion_decisions_evaluation_created",
    }.issubset(REQUIRED_V21_INDEXES)


def test_v121_migration_is_auditable_and_does_not_add_production_switch() -> None:
    source = (ROOT / "migrations" / "versions" / "0030_search_promotion_gates.py").read_text(encoding="utf-8")
    assert 'revision: str = "0030_search_promotion_gates"' in source
    assert 'down_revision: str | None = "0029_multilingual_reranking_experiments"' in source
    assert '"search_promotion_policies"' in source
    assert '"search_promotion_evaluations"' in source
    assert '"search_promotion_decisions"' in source
    assert "production_enabled" not in source
    assert "auto_promote" not in source


def test_promotion_gate_passes_only_when_quality_latency_coverage_and_slices_pass() -> None:
    policy = SearchPromotionPolicy(required_languages=("en", "hi"))
    result = assess_search_promotion(_input(), policy)
    assert result.state == SearchPromotionState.PASS
    assert not result.failures
    assert any(item.key == "required_slice:language:hi" for item in result.checks)


def test_promotion_gate_rejects_semantic_coverage_and_slice_regression() -> None:
    policy = SearchPromotionPolicy(required_languages=("hi",), max_slice_ndcg_drop=0.03)
    metrics = _input(
        semantic_coverage=0.72,
        hybrid_slices={"language": {"en": {"judged_query_count": 20, "ndcg@10": 0.84}, "hi": {"judged_query_count": 12, "ndcg@10": 0.60}}},
    )
    result = assess_search_promotion(metrics, policy)
    assert result.state == SearchPromotionState.FAIL
    assert any("semantic-index coverage" in item for item in result.failures)
    assert any("'hi'" in item and "regresses" in item for item in result.failures)


def test_promotion_gate_rejects_insufficient_required_slice_evidence() -> None:
    policy = SearchPromotionPolicy(required_languages=("hi",), min_slice_judged_queries=10)
    metrics = _input(
        lexical_slices={"language": {"hi": {"judged_query_count": 3, "ndcg@10": 0.70}}},
        hybrid_slices={"language": {"hi": {"judged_query_count": 3, "ndcg@10": 0.74}}},
    )
    result = assess_search_promotion(metrics, policy)
    assert result.state == SearchPromotionState.FAIL
    assert any("too few judged queries" in item for item in result.failures)


def test_v121_service_computes_current_version_semantic_freshness_and_persists_gate() -> None:
    source = (SRC / "application" / "search" / "quality_service.py").read_text(encoding="utf-8")
    assert "semantic_content_sha256 == ArticleVersionModel.content_sha256" in source
    assert "semantic_model == expected_model" in source
    assert "_latest_comparable_runs" in source
    assert "SearchPromotionEvaluationModel(" in source
    assert "PASS means" in (SRC / "domain" / "search" / "promotion.py").read_text(encoding="utf-8")


def test_v121_api_and_ui_expose_gate_without_automatic_promotion() -> None:
    routes = (ROUTES / "search_quality.py").read_text(encoding="utf-8")
    ui = (ROUTES / "search_quality_dashboard.py").read_text(encoding="utf-8")
    assert '"/search-quality/semantic-coverage"' in routes
    assert '"/search-quality/{benchmark_set}/promotion-policy"' in routes
    assert '"/search-quality/{benchmark_set}/promotion-gate/evaluate"' in routes
    assert '"/search-quality/promotion-gate/{evaluation_id}/decisions"' in routes
    assert "Promotion gate" in ui
    assert "Record human decision" in ui
    assert "PASS never enables reranking automatically" in ui
    assert "Semantic index coverage" in ui


def test_human_release_decision_is_separate_and_pass_gated() -> None:
    service = (SRC / "application" / "search" / "quality_service.py").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "versions" / "0030_search_promotion_gates.py").read_text(encoding="utf-8")
    assert 'command.decision == "approve_candidate" and evaluation.state != SearchPromotionState.PASS.value' in service
    assert "only a PASS gate evaluation can be approved as a release candidate" in service
    assert '"search_promotion_decisions"' in migration
    assert "production_enabled" not in service
