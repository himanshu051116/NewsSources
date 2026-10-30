from __future__ import annotations

from pathlib import Path

import pytest

from newsintel import __version__
from newsintel.application.search.dto import SearchBenchmarkRunCommand
from newsintel.application.search.rerank_service import reciprocal_rank_fusion_score
from newsintel.application.search.service import _RESULTS_SQL, SearchFilters
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION, REQUIRED_V20_INDEXES
from newsintel.domain.search.query_language import (
    detect_script,
    language_filter_hint,
    normalize_query,
    use_english_stemming,
)

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "newsintel"
ROUTES = SRC / "api" / "routes"


def test_v120_release_contract_and_indexes() -> None:
    assert __version__ == "1.25.0"
    assert EXPECTED_SCHEMA_REVISION == "0034_article_revision_history"
    assert "ix_article_versions_search_english_fts" in REQUIRED_V20_INDEXES
    assert "ix_article_claims_search_english_fts" in REQUIRED_V20_INDEXES
    assert "ix_events_search_english_fts" in REQUIRED_V20_INDEXES


def test_v120_migration_adds_concurrent_english_fts_indexes() -> None:
    source = (ROOT / "migrations" / "versions" / "0029_multilingual_reranking_experiments.py").read_text(encoding="utf-8")
    assert 'revision: str = "0029_multilingual_reranking_experiments"' in source
    assert 'down_revision: str | None = "0028_entity_resolution_benchmark_expansion"' in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_article_versions_search_english_fts" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_article_claims_search_english_fts" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_search_english_fts" in source


def test_query_normalization_and_script_detection_do_not_rewrite_intent() -> None:
    assert normalize_query("  कोयला   सुरक्षा  ") == "कोयला सुरक्षा"
    assert detect_script("कोयला सुरक्षा") == "devanagari"
    assert language_filter_hint("devanagari") is None
    assert detect_script("coal safety") == "latin"
    assert language_filter_hint("latin") is None
    assert detect_script("coal सुरक्षा") == "mixed"


def test_english_stemming_is_explicitly_script_and_language_guarded() -> None:
    assert use_english_stemming("regulations", None) is True
    assert use_english_stemming("regulations", "en") is True
    assert use_english_stemming("regulations", "hi") is False
    assert use_english_stemming("नियमों", None) is False


def test_ranked_search_sql_keeps_simple_path_and_adds_english_fallback() -> None:
    assert "websearch_to_tsquery('simple', :query)" in _RESULTS_SQL
    assert "websearch_to_tsquery('english', :query)" in _RESULTS_SQL
    assert ":use_english_stemming" in _RESULTS_SQL
    assert "to_tsvector('english', coalesce(av.text_content, ''))" in _RESULTS_SQL
    assert "to_tsvector('english', coalesce(c.claim_text, ''))" in _RESULTS_SQL
    assert "to_tsvector('english', coalesce(e.title, ''))" in _RESULTS_SQL


def test_rrf_semantic_signal_only_reorders_when_present() -> None:
    lexical_only = reciprocal_rank_fusion_score(lexical_rank=1, semantic_rank=None)
    semantic_supported = reciprocal_rank_fusion_score(lexical_rank=3, semantic_rank=1)
    assert semantic_supported > lexical_only
    with pytest.raises(ValueError):
        reciprocal_rank_fusion_score(lexical_rank=0, semantic_rank=None)


def test_hybrid_benchmark_mode_is_explicit_and_not_default() -> None:
    lexical = SearchBenchmarkRunCommand()
    hybrid = SearchBenchmarkRunCommand(search_mode="hybrid_article_rerank")
    assert lexical.search_mode == "lexical"
    assert hybrid.search_mode == "hybrid_article_rerank"


def test_v120_ui_exposes_suggestion_only_assistance_and_controlled_experiment() -> None:
    search_ui = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    quality_ui = (ROUTES / "search_quality_dashboard.py").read_text(encoding="utf-8")
    content = (ROUTES / "content.py").read_text(encoding="utf-8")
    assert "/api/v1/search/assist" in search_ui
    assert "Suggestions (click to use):" in search_ui
    assert 'value="hybrid_article_rerank"' in quality_ui
    assert "Hybrid reranking is experiment-only" in quality_ui
    assert '"/search/assist"' in content
    assert 'include_entities=Permission.CLAIMS_VIEW.value in auth.permissions' in content


def test_entity_only_filter_guard_remains_intact() -> None:
    with pytest.raises(ValueError):
        SearchFilters(result_type="entity", language="hi").normalized(include_claims=True, include_entities=True)
