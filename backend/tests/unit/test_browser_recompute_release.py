from uuid import uuid4

import pytest

from newsintel import __version__
from newsintel.application.historical.enrichment_service import (
    LeasedHistoricalEnrichmentJob,
    _historical_dependency_sources,
)
from newsintel.application.sources.dto import UpdatePublisherExtractionProfileCommand
from newsintel.core.schema import (
    EXPECTED_SCHEMA_REVISION,
    REQUIRED_V15_COLUMNS,
    REQUIRED_V15_INDEXES,
    REQUIRED_V15_TABLES,
)


def test_browser_recompute_release_contract() -> None:
    assert __version__ == "1.25.0"
    assert EXPECTED_SCHEMA_REVISION == "0033_grounded_news_explainer"
    assert "derived_artifact_dependencies" in REQUIRED_V15_TABLES
    assert "derived_artifact_states" in REQUIRED_V15_TABLES
    assert "derived_recompute_jobs" in REQUIRED_V15_TABLES
    assert "ix_derived_recompute_due" in REQUIRED_V15_INDEXES
    assert ("publisher_extraction_profiles", "browser_render_enabled") in REQUIRED_V15_COLUMNS


def test_browser_profile_rejects_urls_as_asset_domains() -> None:
    with pytest.raises(ValueError, match="host/domain names only"):
        UpdatePublisherExtractionProfileCommand(
            browser_render_enabled=True,
            browser_allowed_domains=["https://cdn.example.com/assets"],
        )


def test_historical_dependency_sources_include_current_and_prior_records() -> None:
    article_id = uuid4()
    version_id = uuid4()
    event_id = uuid4()
    prior_version_id = uuid4()
    prior_article_id = uuid4()
    job = LeasedHistoricalEnrichmentJob(
        id=uuid4(),
        article_id=article_id,
        article_version_id=version_id,
        event_id=event_id,
        cutoff_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        attempt_count=1,
    )
    sources = _historical_dependency_sources(
        job=job,
        claims=[],
        same_event=[
            {
                "article_id": str(prior_article_id),
                "article_version_id": str(prior_version_id),
            }
        ],
        prior_claims=[],
        internal_matches=[],
    )
    keys = {(item["kind"], item["id"]) for item in sources}
    assert ("article", str(article_id)) in keys
    assert ("article_version", str(version_id)) in keys
    assert ("event", str(event_id)) in keys
    assert ("article_version", str(prior_version_id)) in keys
