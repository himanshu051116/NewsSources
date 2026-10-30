"""Reader preferences, prepared excerpts and bounded correction refresh."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_article_repository_postgres import persistence as _persistence_fixture

from newsintel.adapters.extractors.article_html import ExtractedArticle
from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.digests import (
    DigestFilters,
    NewsDigestService,
    ReadingPreferences,
    StreamInput,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.digest_quality import EXCERPT_POLICY
from newsintel.infrastructure.db.acquisition_repositories import SqlAlchemyFrontierRepository
from newsintel.infrastructure.db.article_processing_repository import (
    SqlAlchemyArticleProcessingRepository,
)
from newsintel.infrastructure.db.models import (
    ArticleModel,
    ArticleVersionModel,
    PlatformUserModel,
    UrlCandidateModel,
)
from newsintel.maintenance.prepare_digest_excerpts import prepare_recent_excerpts

pytestmark = pytest.mark.integration
persistence = _persistence_fixture


async def ingest(factory, text, digest):
    now = datetime.now(UTC)
    repo = SqlAlchemyArticleProcessingRepository(factory)
    candidate, = await repo.lease_due_candidates(worker_id="reader-test", limit=1, lease_seconds=120)
    run = await repo.start_fetch(candidate_id=candidate.id, worker_id="reader-test",
        trace_id=uuid4(), started_at=now, lease_version=candidate.lease_version)
    fetched = FetchResult(requested_url=candidate.normalized_url, final_url=candidate.normalized_url,
        status_code=200, headers={}, body=b"report", body_sha256=digest*64,
        retrieved_at=now, redirect_chain=())
    extracted = ExtractedArticle(title="Central bank announces interest rate policy", byline=None,
        published_at=now, modified_at=None, language="en", canonical_url=candidate.normalized_url,
        text_content=text, content_sha256=digest*64, extraction_method="test", metadata={}, warnings=())
    return await repo.complete_success(candidate=candidate, run=run, fetched=fetched,
                                       extracted=extracted, raw_artifact=None, completed_at=now)


@pytest.mark.asyncio
async def test_recent_rediscovery_fetches_a_corrected_version_once_per_day(persistence):
    factory, candidate_id, _ = persistence
    first = await ingest(factory, "The central bank said interest rates would fall by 0.25 percent.", "b")
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        row = await session.get(UrlCandidateModel, candidate_id)
        row.last_fetch_at = now-timedelta(hours=25)
    async with factory() as session, session.begin():
        repo = SqlAlchemyFrontierRepository(session)
        candidate = await repo.update_candidate_job_metadata(candidate_id=candidate_id,
            published_at=now, discovered_at=now)
        assert candidate.state == "ready"
    second = await ingest(factory, "The central bank corrected its decision: interest rates remain unchanged.", "c")
    async with factory() as session, session.begin():
        candidate = await SqlAlchemyFrontierRepository(session).update_candidate_job_metadata(
            candidate_id=candidate_id, published_at=now, discovered_at=now)
        assert candidate.state == "processed"
        versions = (await session.scalars(select(ArticleVersionModel).where(
            ArticleVersionModel.article_id == first.article_id))).all()
        assert first.article_id == second.article_id
        assert len(versions) == 2
        assert all(v.metadata_["digest_excerpt"]["policy"] == EXCERPT_POLICY for v in versions)


@pytest.mark.asyncio
async def test_archive_dates_and_active_or_rejected_candidates_are_not_revived(persistence):
    factory, candidate_id, _ = persistence
    result = await ingest(factory, "The central bank said interest rates would fall by 0.25 percent.", "b")
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        row = await session.get(UrlCandidateModel, candidate_id)
        row.last_fetch_at = now-timedelta(hours=25)
        article = await session.get(ArticleModel, result.article_id)
        article.published_at = now-timedelta(days=30)
        for state in ("processed", "leased", "rejected"):
            row.state = state
            await session.flush()
            candidate = await SqlAlchemyFrontierRepository(session).update_candidate_job_metadata(
                candidate_id=candidate_id, published_at=now, discovered_at=now)
            assert candidate.state == state


@pytest.mark.asyncio
async def test_preferences_are_owned_and_saved_feed_deletion_clears_the_default(persistence):
    factory, _, _ = persistence
    now = datetime.now(UTC)
    owners = [uuid7(), uuid7()]
    async with factory() as session, session.begin():
        for owner in owners:
            session.add(PlatformUserModel(id=owner, auth_provider="test",
                auth_provider_user_id=str(owner), role="viewer", access_status="approved",
                requested_at=now, created_at=now, updated_at=now, metadata_={"keep":"yes"}))
    service = NewsDigestService(factory)
    stream = await service.save_stream(owners[0], StreamInput(name="Science", filters=DigestFilters(topics=["science_health"])))
    prefs = ReadingPreferences(period="weekly", stream_id=stream.id)
    with pytest.raises(LookupError):
        await service.save_preferences(owners[1], prefs)
    await service.save_preferences(owners[0], prefs)
    restored = await service.preferences(owners[0])
    assert restored.period == "weekly" and restored.filters.topics == ["science_health"]
    assert (await service.preferences(owners[1])).stream_id is None
    await service.delete_stream(owners[0], stream.id)
    assert await service.preferences(owners[0]) == ReadingPreferences()
    async with factory() as session:
        assert (await session.get(PlatformUserModel, owners[0])).metadata_["keep"] == "yes"


@pytest.mark.asyncio
async def test_excerpt_backfill_preserves_other_metadata_and_skips_prepared_versions(persistence):
    factory, _, _ = persistence
    result = await ingest(factory, "The central bank said interest rates would fall by 0.25 percent.", "b")
    async with factory() as session, session.begin():
        row = await session.get(ArticleVersionModel, result.version_id)
        row.metadata_ = {"unrelated":"preserved"}
    assert await prepare_recent_excerpts(factory, limit=1) == 1
    async with factory() as session:
        row = await session.get(ArticleVersionModel, result.version_id)
        assert row.metadata_["unrelated"] == "preserved"
        assert row.metadata_["digest_excerpt"]["sentence"]
    assert await prepare_recent_excerpts(factory, limit=1) == 0
