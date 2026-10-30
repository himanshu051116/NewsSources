from datetime import UTC, datetime, timedelta

from newsintel.domain.intelligence.historical_enrichment import (
    build_historical_queries,
    historical_depth,
    timeline_summary,
)


def test_build_historical_queries_uses_entities_and_title_terms() -> None:
    queries = build_historical_queries(
        title="Reserve Bank raises policy rate after inflation report",
        claim_features=[{"entities": ["Reserve Bank", "India"]}],
    )
    assert queries
    assert "Reserve Bank" in queries[0]
    assert len(queries) <= 3


def test_historical_depth_rewards_multiple_independent_context_channels() -> None:
    assert historical_depth(
        same_event_count=2,
        prior_claim_count=3,
        internal_match_count=4,
        external_match_count=2,
    ) == "deep"
    assert historical_depth(
        same_event_count=0,
        prior_claim_count=0,
        internal_match_count=0,
        external_match_count=0,
    ) == "none"


def test_timeline_summary_excludes_future_observations() -> None:
    cutoff = datetime(2026, 8, 14, tzinfo=UTC)
    summary = timeline_summary(
        [cutoff - timedelta(days=10), cutoff - timedelta(days=2), cutoff + timedelta(days=1)],
        cutoff_at=cutoff,
    )
    assert summary["historical_item_count"] == 2
    assert summary["span_days"] == 8

from newsintel.domain.intelligence.historical_enrichment import (
    classify_claim_evolution,
    deduplicate_history_items,
    historical_context_confidence,
    historical_relevance_score,
    normalize_history_url,
    summarize_change_pattern,
)


def test_history_url_normalization_removes_tracking_noise() -> None:
    assert normalize_history_url("https://Example.com/story/?utm_source=x&id=7#top") == (
        "https://example.com/story?id=7"
    )


def test_history_dedup_keeps_stronger_match() -> None:
    items, dropped = deduplicate_history_items(
        [
            {"url": "https://example.com/a?utm_source=x", "relevance_score": 0.2},
            {"url": "https://example.com/a", "relevance_score": 0.8},
        ]
    )
    assert dropped == 1
    assert len(items) == 1
    assert items[0]["relevance_score"] == 0.8


def test_relevance_score_is_explicitly_contextual_not_truth() -> None:
    result = historical_relevance_score(
        same_event=True,
        claim_family_match=True,
        entity_overlap=0.8,
        lexical_overlap=0.7,
    )
    assert result["score"] >= 0.8
    assert result["scope"] == "historical_linkage_not_factual_truth"


def test_context_confidence_penalizes_duplicates_and_rewards_diversity() -> None:
    strong = historical_context_confidence(
        relevance_scores=[0.9, 0.8, 0.7],
        source_diversity_count=4,
        channel_count=3,
        duplicate_count=0,
    )
    weak = historical_context_confidence(
        relevance_scores=[0.4, 0.3],
        source_diversity_count=1,
        channel_count=1,
        duplicate_count=8,
    )
    assert strong["score"] > weak["score"]


def test_claim_evolution_distinguishes_revision_candidate() -> None:
    assert classify_claim_evolution(
        numeric_changed=True,
        temporal_changed=False,
        text_changed=True,
        same_temporal_reference=True,
    ) == "numeric_revision_candidate"


def test_change_pattern_surfaces_revision_candidates() -> None:
    assert summarize_change_pattern(
        current_claim_count=4,
        new_claim_count=1,
        recurring_claim_count=3,
        changed_claim_count=2,
        revision_candidate_count=1,
    ) == "possible_conflict_or_revision"


def test_history_dedup_preserves_distinct_prior_versions_of_same_article() -> None:
    items, dropped = deduplicate_history_items(
        [
            {
                "url": "https://example.com/story",
                "article_version_id": "v1",
                "relationship": "same_article_prior_version",
                "relevance_score": 0.9,
            },
            {
                "url": "https://example.com/story",
                "article_version_id": "v2",
                "relationship": "same_article_prior_version",
                "relevance_score": 0.95,
            },
        ]
    )
    assert dropped == 0
    assert len(items) == 2


def test_build_historical_queries_preserves_hindi_terms() -> None:
    queries = build_historical_queries(
        title="दिल्ली चुनाव में मतदान शुरू",
        claim_features=[{"entities": ["भारत निर्वाचन आयोग", "दिल्ली"]}],
    )
    assert queries
    assert any("दिल्ली" in query for query in queries)
    assert any("चुनाव" in query or "मतदान" in query for query in queries)
