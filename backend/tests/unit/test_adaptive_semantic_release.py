from newsintel import __version__
from newsintel.core.schema import (
    REQUIRED_V14_COLUMNS,
    REQUIRED_V14_INDEXES,
    REQUIRED_V14_TABLES,
)
from newsintel.main import create_app


def test_adaptive_semantic_release_contract() -> None:
    assert tuple(int(part) for part in __version__.split(".")) >= (1, 10, 0)
    assert "publisher_extraction_profiles" in REQUIRED_V14_TABLES
    assert "ix_publisher_extraction_profiles_domain" in REQUIRED_V14_INDEXES
    assert "ix_article_versions_semantic_pending" in REQUIRED_V14_INDEXES
    assert ("article_versions", "semantic_indexed_at") in REQUIRED_V14_COLUMNS
    assert ("article_versions", "semantic_model") in REQUIRED_V14_COLUMNS
    assert ("article_versions", "semantic_content_sha256") in REQUIRED_V14_COLUMNS


def test_adaptive_extraction_routes_are_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/publishers/{publisher_id}/extraction-profile" in paths
