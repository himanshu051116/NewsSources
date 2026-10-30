from __future__ import annotations

from pathlib import Path
from uuid import UUID

from newsintel import __version__
from newsintel.application.intelligence.entity_resolution_review_service import _candidate_key
from newsintel.application.search.quality_service import _slice_aggregates, _slow_diagnosis
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION, REQUIRED_V19_COLUMNS, REQUIRED_V19_INDEXES, REQUIRED_V19_TABLES
from newsintel.infrastructure.db.models import SearchBenchmarkQueryModel, SearchQueryObservationModel

ROOT = Path(__file__).resolve().parents[2]


def test_v119_release_contract() -> None:
    assert __version__ == "1.25.0"
    assert EXPECTED_SCHEMA_REVISION == "0034_article_revision_history"
    assert "entity_resolution_candidates" in REQUIRED_V19_TABLES
    assert "entity_resolution_actions" in REQUIRED_V19_TABLES
    assert "ix_canonical_entities_resolution_status" in REQUIRED_V19_INDEXES
    assert ("canonical_entities", "resolution_status") in REQUIRED_V19_COLUMNS
    assert ("canonical_entities", "merged_into_entity_id") in REQUIRED_V19_COLUMNS


def test_v119_migration_contains_resolution_audit_tables() -> None:
    source = (ROOT / "migrations" / "versions" / "0028_entity_resolution_benchmark_expansion.py").read_text(encoding="utf-8")
    assert 'revision: str = "0028_entity_resolution_benchmark_expansion"' in source
    assert 'down_revision: str | None = "0027_search_quality_entity_intelligence"' in source
    assert '"entity_resolution_candidates"' in source
    assert '"entity_resolution_actions"' in source
    assert '"resolution_status"' in source
    assert '"merged_into_entity_id"' in source


def test_conflict_candidate_key_is_order_independent() -> None:
    a = UUID("00000000-0000-0000-0000-000000000001")
    b = UUID("00000000-0000-0000-0000-000000000002")
    left = _candidate_key("shared_normalized_identity", "coal india", [a, b])
    right = _candidate_key("shared_normalized_identity", "coal india", [b, a])
    assert left == right


def test_search_excludes_merged_entities() -> None:
    global_search = (ROOT / "src" / "newsintel" / "application" / "search" / "service.py").read_text(encoding="utf-8")
    entity_search = (ROOT / "src" / "newsintel" / "application" / "intelligence" / "entity_intelligence_service.py").read_text(encoding="utf-8")
    assert "coalesce(e.resolution_status, 'active') = 'active'" in global_search
    assert "coalesce(e.resolution_status, 'active') = 'active'" in entity_search


def test_entity_resolution_static_routes_precede_uuid_routes() -> None:
    source = (ROOT / "src" / "newsintel" / "api" / "routes" / "entities.py").read_text(encoding="utf-8")
    assert source.index('@router.post("/entities/resolution/scan"') < source.index('@router.get("/entities/{entity_id}/profile"')
    assert source.index('@router.get("/entities/resolution/actions"') < source.index('@router.get("/entities/{entity_id}/profile"')


def test_slice_aggregates_report_language_and_topic_coverage() -> None:
    q1 = SearchBenchmarkQueryModel(language="en", topic_key="coal", result_type="article")
    q2 = SearchBenchmarkQueryModel(language="hi", topic_key="coal", result_type="article")
    rows = [
        (q1, {"mrr": 1.0, "ndcg@10": 1.0}, True, True),
        (q2, {"mrr": 0.0, "ndcg@10": 0.2}, False, False),
    ]
    payload = _slice_aggregates(rows, ["language", "topic_key"])
    assert payload["language"]["en"]["query_count"] == 1
    assert payload["language"]["hi"]["judgment_coverage"] == 0.0
    assert payload["topic_key"]["coal"]["query_count"] == 2


def test_slow_diagnosis_is_privacy_preserving_and_actionable() -> None:
    items = [
        SearchQueryObservationModel(duration_ms=1800, result_count=9000, returned_count=20, cursor_page=False),
        SearchQueryObservationModel(duration_ms=2100, result_count=8700, returned_count=20, cursor_page=True),
    ]
    findings = _slow_diagnosis("all", {}, items)
    assert any("Broad all-type" in item for item in findings)
    assert any("Large matching corpus" in item for item in findings)
    assert all("query text" not in item.casefold() for item in findings)


def test_v119_dashboards_expose_human_resolution_and_benchmark_portability() -> None:
    entity_ui = (ROOT / "src" / "newsintel" / "api" / "routes" / "entity_dashboard.py").read_text(encoding="utf-8")
    quality_ui = (ROOT / "src" / "newsintel" / "api" / "routes" / "search_quality_dashboard.py").read_text(encoding="utf-8")
    assert "Review matching names" in entity_ui
    assert "Confirm merge" in entity_ui
    assert "Split alias into new entity" in entity_ui
    assert "Export JSON" in quality_ui
    assert "Import benchmark JSON" in quality_ui
    assert "Slow-query diagnostics" in quality_ui
