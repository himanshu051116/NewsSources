from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from newsintel.application.search.service import (
    SearchFilters,
    _RESULTS_SQL,
    _decode_cursor,
    _encode_cursor,
    _search_fingerprint,
)
from newsintel.core.schema import (
    EXPECTED_SCHEMA_REVISION,
    REQUIRED_V18_INDEXES,
    REQUIRED_V18_TABLES,
)
from newsintel.domain.search.metrics import ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "newsintel"
ROUTES = SRC / "api" / "routes"


def test_v118_schema_requires_search_quality_and_entity_intelligence() -> None:
    assert EXPECTED_SCHEMA_REVISION == "0034_article_revision_history"
    assert {
        "search_benchmark_queries",
        "search_relevance_judgments",
        "search_benchmark_runs",
        "search_query_observations",
        "entity_mentions",
    }.issubset(set(REQUIRED_V18_TABLES))
    assert {
        "ix_canonical_entities_search_fts",
        "ix_entity_aliases_search_fts",
        "ix_search_query_observations_created",
        "ix_entity_mentions_entity_created",
    }.issubset(set(REQUIRED_V18_INDEXES))


def test_v118_migration_adds_benchmark_entity_tables_and_concurrent_entity_indexes() -> None:
    source = (ROOT / "migrations" / "versions" / "0027_search_quality_entity_intelligence.py").read_text(encoding="utf-8")
    assert 'revision: str = "0027_search_quality_entity_intelligence"' in source
    assert 'down_revision: str | None = "0026_search_infrastructure"' in source
    assert '"search_benchmark_queries"' in source
    assert '"search_relevance_judgments"' in source
    assert '"search_query_observations"' in source
    assert '"entity_mentions"' in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_canonical_entities_search_fts" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_entity_aliases_search_fts" in source


def test_rank_metrics_are_deterministic_and_grade_aware() -> None:
    a = ("article", "a")
    b = ("article", "b")
    c = ("article", "c")
    x = ("article", "x")
    grades = {a: 3, b: 2, c: 1}
    ranked = [b, x, a]
    assert precision_at_k(ranked, grades, 3) == pytest.approx(2 / 3)
    assert recall_at_k(ranked, grades, 3) == pytest.approx(2 / 3)
    assert reciprocal_rank(ranked, grades) == 1.0
    value = ndcg_at_k(ranked, grades, 3)
    assert value is not None and 0.0 < value < 1.0
    assert recall_at_k(ranked, {}, 3) is None
    assert ndcg_at_k(ranked, {}, 3) is None


def test_entity_search_requires_analyst_scope_and_cursor_accepts_entity() -> None:
    with pytest.raises(ValueError, match="entity search requires analyst"):
        SearchFilters(result_type="entity").normalized(include_claims=False, include_entities=False)
    filters = SearchFilters(result_type="entity").normalized(include_claims=True, include_entities=True)
    fingerprint = _search_fingerprint("coal india", filters, True, True)
    when = datetime(2026, 10, 6, 4, 30, tzinfo=UTC)
    item_id = uuid4()
    cursor = _encode_cursor(
        fingerprint=fingerprint,
        snapshot_at=when,
        score=0.72,
        occurred_at=when,
        result_type="entity",
        item_id=item_id,
    )
    decoded = _decode_cursor(cursor, expected_fingerprint=fingerprint)
    assert decoded["result_type"] == "entity"
    assert decoded["id"] == str(item_id)


def test_global_search_sql_includes_entity_registry_without_fuzzy_identity_linking() -> None:
    assert "entity_matches AS" in _RESULTS_SQL
    assert "canonical_entities e" in _RESULTS_SQL
    assert "entity_aliases ea" in _RESULTS_SQL
    assert ":include_entities = true" in _RESULTS_SQL
    assert "to_tsvector('simple', coalesce(e.canonical_name, ''))" in _RESULTS_SQL


def test_entity_intelligence_service_is_precision_first() -> None:
    source = (SRC / "application" / "intelligence" / "entity_intelligence_service.py").read_text(encoding="utf-8")
    assert "exact_canonical" in source
    assert "exact_alias" in source
    assert "normalize_entity_name" in source
    assert "fuzzy matches are never linked" in source
    assert "SequenceMatcher" not in source


def test_search_quality_service_measures_mrr_ndcg_recall_and_latency() -> None:
    source = (SRC / "application" / "search" / "quality_service.py").read_text(encoding="utf-8")
    assert 'metrics[f"precision@{k}"]' in source
    assert 'metrics[f"recall@{k}"]' in source
    assert 'metrics[f"ndcg@{k}"]' in source
    assert '"mrr": reciprocal_rank' in source
    assert '"p95_ms"' in source
    assert "judgment_coverage" in source
    assert "record_telemetry=False" in source


def test_v118_dashboards_expose_entities_and_search_quality_without_semantic_claims() -> None:
    search = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    entities = (ROUTES / "entity_dashboard.py").read_text(encoding="utf-8")
    quality = (ROUTES / "search_quality_dashboard.py").read_text(encoding="utf-8")
    assert 'data-type="entity"' in search
    assert "mEntities" in search
    assert "/entities/${" in search
    assert "Exact normalized canonical/alias links only" in entities
    assert "Absence here does not mean the entity is absent" in entities
    assert "Recall" not in quality or "Search Quality" in quality
    assert "semantic" in quality.lower()
    assert "judgment coverage" in quality.lower()


def test_v118_routes_expose_entity_profiles_benchmark_and_telemetry() -> None:
    entities = (ROUTES / "entities.py").read_text(encoding="utf-8")
    quality = (ROUTES / "search_quality.py").read_text(encoding="utf-8")
    content = (ROUTES / "content.py").read_text(encoding="utf-8")
    assert '"/entities/search"' in entities
    assert '"/entities/{entity_id}/profile"' in entities
    assert '"/entities/{entity_id}/refresh-mentions"' in entities
    assert '"/search-quality/telemetry"' in quality
    assert '"/search-quality/{benchmark_set}/evaluate"' in quality
    assert "include_entities=include_entities" in content
    assert "claim|entity" in content


def test_entity_only_search_rejects_article_specific_filters() -> None:
    with pytest.raises(ValueError, match="do not apply to entity-only search"):
        SearchFilters(result_type="entity", language="en").normalized(include_claims=True, include_entities=True)
    with pytest.raises(ValueError, match="do not apply to entity-only search"):
        SearchFilters(result_type="entity", publisher="Reuters").normalized(include_claims=True, include_entities=True)
