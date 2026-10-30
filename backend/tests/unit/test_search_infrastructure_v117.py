from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from newsintel.application.search.service import (
    InvalidSearchCursorError,
    SearchFilters,
    _RESULTS_SQL,
    _decode_cursor,
    _encode_cursor,
    _literal_like_pattern,
    _search_fingerprint,
)
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION, REQUIRED_V17_INDEXES

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "newsintel"
ROUTES = SRC / "api" / "routes"


def test_v117_schema_head_and_search_indexes_are_release_required() -> None:
    assert EXPECTED_SCHEMA_REVISION == "0033_grounded_news_explainer"
    required = set(REQUIRED_V17_INDEXES)
    assert "ix_article_versions_fts_simple" in required
    assert "ix_article_versions_search_weighted_fts" in required
    assert "ix_events_search_fts" in required
    assert "ix_article_claims_search_fts" in required
    assert "ix_articles_language_published" in required
    assert "ix_articles_publisher_published" in required


def test_v117_migration_adds_weighted_article_index_and_event_claim_indexes_concurrently() -> None:
    source = (ROOT / "migrations" / "versions" / "0026_search_infrastructure.py").read_text(encoding="utf-8")
    assert 'revision: str = "0026_search_infrastructure"' in source
    assert 'down_revision: str | None = "0025_collaboration_monitoring"' in source
    assert "setweight(to_tsvector('simple', coalesce(title, '')), 'A')" in source
    assert "ix_article_versions_search_weighted_fts" in source
    assert "CREATE INDEX CONCURRENTLY" in source
    assert "ix_events_search_fts" in source
    assert "ix_article_claims_search_fts" in source


def test_search_sql_uses_ranked_postgres_fts_and_latest_version_guard() -> None:
    assert "websearch_to_tsquery('simple', :query)" in _RESULTS_SQL
    assert "ts_rank_cd" in _RESULTS_SQL
    assert "ORDER BY score DESC, occurred_at DESC, result_type ASC, id ASC" in _RESULTS_SQL
    assert "newer.version_number > av.version_number" in _RESULTS_SQL
    assert "newer.created_at <= :snapshot_at" in _RESULTS_SQL
    assert "to_tsvector('simple', coalesce(c.claim_text, '')) @@ s.tsq" in _RESULTS_SQL


def test_search_filter_normalization_and_date_validation() -> None:
    filters = SearchFilters(result_type="ARTICLE", language=" EN ", publisher=" Reuters ").normalized(
        include_claims=False
    )
    assert filters.result_type == "article"
    assert filters.language == "en"
    assert filters.publisher == "Reuters"
    with pytest.raises(ValueError, match="claim-view"):
        SearchFilters(result_type="claim").normalized(include_claims=False)
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="from_date"):
        SearchFilters(from_date=now, to_date=now - timedelta(days=1)).normalized(include_claims=True)


def test_cursor_is_query_bound_and_round_trips_snapshot_and_sort_key() -> None:
    filters = SearchFilters(result_type="all", language="en").normalized(include_claims=True)
    fingerprint = _search_fingerprint("coal safety", filters, True)
    snapshot = datetime(2026, 10, 6, 4, 0, tzinfo=UTC)
    occurred = datetime(2026, 10, 5, 18, 30, tzinfo=UTC)
    item_id = uuid4()
    cursor = _encode_cursor(
        fingerprint=fingerprint,
        snapshot_at=snapshot,
        score=0.812345678,
        occurred_at=occurred,
        result_type="article",
        item_id=item_id,
    )
    decoded = _decode_cursor(cursor, expected_fingerprint=fingerprint)
    assert decoded["snapshot_at"] == snapshot
    assert decoded["occurred_at"] == occurred
    assert decoded["score"] == pytest.approx(0.81234568)
    assert decoded["result_type"] == "article"
    assert decoded["id"] == str(item_id)
    with pytest.raises(InvalidSearchCursorError, match="does not match"):
        _decode_cursor(cursor, expected_fingerprint="different-query")


def test_publisher_like_filter_escapes_user_wildcards() -> None:
    assert _literal_like_pattern(r"100%_wire\\desk") == r"%100\%\_wire\\\\desk%"


def test_search_dashboard_exposes_indexed_filters_and_keyset_load_more() -> None:
    source = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    assert "stored database content" in source
    assert "filterLanguage" in source
    assert "filterPublisher" in source
    assert "filterLifecycle" in source
    assert "loadMoreBtn" in source
    assert "next_cursor" in source
    assert "result_type" in source
    assert "filters={{result_type:f.result_type" in source


def test_search_route_uses_dedicated_service_and_supports_cursor_filters() -> None:
    source = (ROUTES / "content.py").read_text(encoding="utf-8")
    assert "IntelligenceSearchServiceDependency" in source
    assert "cursor: str | None" in source
    assert "result_type: str" in source
    assert "publisher: str | None" in source
    assert "lifecycle_status: str | None" in source
    assert "InvalidSearchCursorError" in source
