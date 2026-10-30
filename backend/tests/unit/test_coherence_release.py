from newsintel.core.schema import REQUIRED_V13_INDEXES
from newsintel.domain.events.matching import POLICY_VERSION
from newsintel.main import create_app


def test_coherence_release_contract() -> None:
    assert POLICY_VERSION == "event-matching-structured-lexical-v4"
    assert "ix_article_versions_fts_simple" in REQUIRED_V13_INDEXES
    assert "ix_article_claims_family_created" in REQUIRED_V13_INDEXES


def test_coherence_routes_are_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/news" in paths
    assert "/articles/{article_id}/intelligence" in paths
    assert "/api/v1/articles/{article_id}/intelligence-state" in paths
    assert "/api/v1/articles/{article_id}/intelligence-stream" in paths
