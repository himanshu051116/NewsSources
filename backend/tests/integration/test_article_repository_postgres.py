"""Run against a separately migrated database with NEWSINTEL_TEST_DATABASE_URL."""

import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from newsintel.adapters.artifacts.local_store import RawFetchArtifact
from newsintel.adapters.extractors.article_html import ExtractedArticle
from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.digests import (
    DigestFilters,
    DigestRequest,
    NewsDigestService,
    StreamInput,
)
from newsintel.application.intelligence.entity_intelligence_service import EntityIntelligenceService
from newsintel.application.search.service import IntelligenceSearchService, SearchFilters
from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.article_processing_repository import (
    SqlAlchemyArticleProcessingRepository,
)
from newsintel.infrastructure.db.base import Base
from newsintel.infrastructure.db.models import (
    ArticleFetchRunModel,
    ArticleModel,
    ArticleVersionModel,
    CanonicalEntityModel,
    EventModel,
    PlatformUserModel,
    PublisherModel,
    UrlCandidateModel,
)

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def persistence():
    url = os.environ.get("NEWSINTEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NEWSINTEL_TEST_DATABASE_URL is not configured")
    if not url.rsplit("/", 1)[-1].startswith("newsintel_audit_"):
        raise ValueError("repository regression tests require a dedicated newsintel_audit_ database")
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(connection, expire_on_commit=False,
                                     join_transaction_mode="create_savepoint")
        now = datetime.now(UTC)
        publisher_id = uuid7()
        token = uuid4().hex
        candidate_id = uuid7()
        async with factory() as session, session.begin():
            session.add(PublisherModel(id=publisher_id, name="Regression source", slug=token,
                        canonical_domain=f"{token}.example.org", created_at=now, updated_at=now))
            await session.flush()
            session.add(UrlCandidateModel(
                id=candidate_id, publisher_id=publisher_id,
                normalized_url=f"https://{token}.example.org/news/important-report",
                url_fingerprint=hashlib.sha256(token.encode()).digest(), state="ready",
                priority_score=1.0, priority_components={}, priority_policy_version="test",
                next_fetch_at=now, published_at=now, first_discovered_at=now,
                created_at=now, updated_at=now,
            ))
        try:
            yield factory, candidate_id, connection
        finally:
            await transaction.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_migrated_schema_contains_every_mapped_column(persistence):
    _, _, connection = persistence

    def compare(sync_connection):
        inspector = inspect(sync_connection)
        missing = []
        for table in Base.metadata.sorted_tables:
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            missing.extend(f"{table.name}.{name}" for name in set(table.columns.keys()) - actual)
        return missing

    assert await connection.run_sync(compare) == []


@pytest.mark.asyncio
async def test_article_success_persists_snapshot_and_fenced_fetch_run(persistence):
    factory, _, _ = persistence
    repository = SqlAlchemyArticleProcessingRepository(factory)
    candidate, = await repository.lease_due_candidates(worker_id="test", limit=1, lease_seconds=120)
    now = datetime.now(UTC)
    run = await repository.start_fetch(candidate_id=candidate.id, worker_id="test",
              trace_id=uuid4(), started_at=now, lease_version=candidate.lease_version)
    fetched = FetchResult(requested_url=candidate.normalized_url, final_url=candidate.normalized_url,
              status_code=200, headers={}, body=b"<html>report</html>", body_sha256="a" * 64,
              retrieved_at=now, redirect_chain=())
    extracted = ExtractedArticle(title="Central bank announces a policy change", byline=None,
                published_at=now, modified_at=None, language="en",
                canonical_url=candidate.normalized_url, text_content="The central bank announced a policy change.",
                content_sha256="b" * 64, extraction_method="test", metadata={}, warnings=())
    result = await repository.complete_success(candidate=candidate, run=run, fetched=fetched,
             extracted=extracted, raw_artifact=RawFetchArtifact("file:///test.html", "local", "a" * 64, 19),
             completed_at=now)
    async with factory() as session:
        row = await session.get(ArticleFetchRunModel, run.id)
        version = await session.get(ArticleVersionModel, result.version_id)
        assert row.status == "succeeded"
        assert row.lease_version == candidate.lease_version
        assert version.metadata_["raw_fetch_artifact"]["artifact_uri"] == "file:///test.html"


@pytest.mark.asyncio
async def test_expired_candidate_is_reclaimed_and_old_writer_is_rejected(persistence):
    factory, candidate_id, _ = persistence
    repository = SqlAlchemyArticleProcessingRepository(factory)
    first, = await repository.lease_due_candidates(worker_id="first", limit=1, lease_seconds=120)
    async with factory() as session, session.begin():
        await session.execute(update(UrlCandidateModel).where(UrlCandidateModel.id == candidate_id)
                              .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    assert not await repository.heartbeat(candidate_id=candidate_id, worker_id="first",
                                         lease_version=first.lease_version, lease_seconds=120)
    second, = await repository.lease_due_candidates(worker_id="second", limit=1, lease_seconds=120)
    assert second.lease_version == first.lease_version + 1
    with pytest.raises(RuntimeError, match="lease lost"):
        await repository.reject_before_fetch(candidate=first, worker_id="first", trace_id=uuid4(),
                 rejected_at=datetime.now(UTC), reason="old", message="stale attempt")
    await repository.reject_before_fetch(candidate=second, worker_id="second", trace_id=uuid4(),
             rejected_at=datetime.now(UTC), reason="old", message="outdated article")
    async with factory() as session:
        row = await session.get(UrlCandidateModel, candidate_id)
        runs = list((await session.scalars(select(ArticleFetchRunModel))).all())
        assert row.state == "rejected"
        assert len(runs) == 1
        assert runs[0].lease_version == second.lease_version


@pytest.mark.asyncio
async def test_search_default_filters_and_tied_score_pagination(persistence):
    factory, _, _ = persistence
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        for _ in range(2):
            event_id = uuid7()
            session.add(EventModel(
                id=event_id, slug=f"event-{event_id.hex}", title="Policy council decision",
                lifecycle_status="active", assignment_status="provisional",
                first_detected_at=now, last_material_change_at=now, metadata_={},
                created_at=now, updated_at=now,
            ))
    service = IntelligenceSearchService(factory)
    filters = SearchFilters(result_type="event")
    first = await service.search(query="policy", filters=filters, limit=1, record_telemetry=False)
    assert first.counts == {"event": 2}
    assert first.next_cursor
    second = await service.search(query="policy", filters=filters, limit=1,
                                  cursor=first.next_cursor, record_telemetry=False)
    assert len(first.results) == len(second.results) == 1
    assert first.results[0].id != second.results[0].id
    assert second.next_cursor is None


@pytest.mark.asyncio
async def test_entity_search_null_and_selected_filters(persistence):
    factory, _, _ = persistence
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        session.add(CanonicalEntityModel(
            id=uuid7(), entity_key=uuid4().hex, canonical_name="Policy Council",
            normalized_name="policy council", entity_type="organization", country_code="IN",
            created_at=now, updated_at=now,
        ))
    service = EntityIntelligenceService(factory)
    result = await service.search("policy")
    assert result.result_count == 1
    assert result.results[0].canonical_name == "Policy Council"
    assert (await service.search("policy", entity_type="organization", country_code="in")).result_count == 1
    assert (await service.search("policy", country_code="US")).result_count == 0


@pytest.mark.asyncio
async def test_news_editions_use_publication_windows_latest_snapshot_and_real_filters(
    persistence, monkeypatch,
):
    factory, candidate_id, _ = persistence
    end = datetime.now(UTC)
    async with factory() as session, session.begin():
        candidate = await session.get(UrlCandidateModel, candidate_id)
        publisher_id = candidate.publisher_id
        event_id = uuid7()
        session.add(EventModel(
            id=event_id, slug=f"digest-{event_id.hex}", title="News digest regression",
            lifecycle_status="active", assignment_status="provisional",
            first_detected_at=end, last_material_change_at=end, metadata_={},
            created_at=end, updated_at=end,
        ))
        await session.flush()

        async def add_report(title, published, language="en", *, version=True):
            article_id = uuid7()
            url = f"https://digest.example/{article_id}"
            session.add(ArticleModel(
                id=article_id, event_id=event_id, publisher_id=publisher_id,
                canonical_url=url, normalized_url_hash=hashlib.sha256(url.encode()).digest(),
                title=title, language=language, published_at=published,
                first_observed_at=end - timedelta(minutes=10),
                created_at=end - timedelta(minutes=10), updated_at=end,
            ))
            await session.flush()
            if version:
                session.add(ArticleVersionModel(
                    id=uuid7(), article_id=article_id, version_number=1,
                    source_url=url, final_url=url, title=title, byline=None, language=language,
                    published_at=published, retrieved_at=end - timedelta(minutes=5),
                    content_sha256=hashlib.sha256(str(article_id).encode()).hexdigest(),
                    text_content=f"Officials said the {title.lower()} was confirmed on Friday.",
                    extraction_method="test", extraction_warnings=[], metadata_={},
                    created_at=end - timedelta(minutes=5),
                ))
            return article_id, url

        recent_id, recent_url = await add_report("Central bank announces lower interest rates",
                                                end - timedelta(hours=1))
        await add_report("Cricket team wins final match", end - timedelta(hours=2), "hi")
        await add_report("University examination timetable released", end - timedelta(days=4))
        # Recently crawled old reporting and future source dates must not become today's news.
        await add_report("Old government policy from the archive", end - timedelta(days=20))
        await add_report("Future government policy", end + timedelta(hours=1))
        await add_report("Local transport reporting has no source timestamp", None, version=False)
        session.add(ArticleVersionModel(
            id=uuid7(), article_id=recent_id, version_number=2, source_url=recent_url,
            final_url=recent_url, title="Future version must not leak into the snapshot",
            byline=None, language="en", published_at=end - timedelta(hours=1),
            retrieved_at=end + timedelta(hours=1), content_sha256="f" * 64,
            text_content="A later version unavailable at this edition's snapshot time.",
            extraction_method="test", extraction_warnings=[], metadata_={},
            created_at=end + timedelta(hours=1),
        ))
    service = NewsDigestService(factory)
    filters = DigestFilters(publisher_ids=[publisher_id])
    daily = await service.edition(DigestRequest(filters=filters, as_of=end))
    assert daily.eligible_reports == daily.matching_reports == daily.story_count == 3
    assert daily.publisher_count == 1
    assert daily.estimated_read_seconds <= 120
    assert not daily.sampled
    assert daily.unavailable_summaries == 1
    assert all(item.summary_available for item in daily.items)
    assert any(item.article_id == recent_id and item.title.startswith("Central bank")
               for item in daily.items)
    weekly = await service.edition(DigestRequest(period="weekly", filters=filters, as_of=end))
    assert weekly.story_count == 4
    english = await service.edition(DigestRequest(
        filters=DigestFilters(publisher_ids=[publisher_id], languages=["en"]), as_of=end,
    ))
    assert english.story_count == 2
    sports = await service.edition(DigestRequest(
        filters=DigestFilters(publisher_ids=[publisher_id], topics=["sports"]), as_of=end,
    ))
    assert sports.story_count == 1
    assert sports.items[0].language == "hi"
    first = await service.edition(DigestRequest(filters=filters, as_of=end,
                                               full_stream=True, page_size=1))
    second = await service.edition(DigestRequest(filters=filters, as_of=first.window_end,
                                                full_stream=True, page_size=1,
                                                offset=first.next_offset))
    assert first.next_offset == 1
    assert first.items[0].article_id != second.items[0].article_id
    full = await service.edition(DigestRequest(filters=filters, as_of=end, full_stream=True))
    assert any(item.date_basis == "first_captured" and not item.summary_available
               for item in full.items)
    with pytest.raises(ValueError, match="future"):
        await service.edition(DigestRequest(as_of=end + timedelta(days=1)))
    monkeypatch.setattr("newsintel.application.digests.MAX_REPORTS", 2)
    limited = await service.edition(DigestRequest(filters=filters, as_of=end))
    assert limited.sampled
    assert limited.eligible_reports == 3
    assert limited.scanned_reports == 2


@pytest.mark.asyncio
async def test_saved_news_streams_are_account_owned_and_preserve_other_metadata(persistence):
    factory, _, _ = persistence
    now = datetime.now(UTC)
    first_user, second_user = uuid7(), uuid7()
    async with factory() as session, session.begin():
        for user_id in (first_user, second_user):
            session.add(PlatformUserModel(
                id=user_id, auth_provider="test", auth_provider_user_id=str(user_id),
                verified_email=None, display_name="Digest reader", avatar_url=None,
                access_status="approved", role="viewer", requested_at=now, approved_at=now,
                metadata_={"unrelated_auth_state": {"keep": True}}, created_at=now, updated_at=now,
            ))
    service = NewsDigestService(factory)
    saved = await service.save_stream(first_user, StreamInput(
        name="Local cricket", period="weekly", filters=DigestFilters(keywords=["cricket"]),
    ))
    assert (await service.streams(first_user))[0].id == saved.id
    assert await service.streams(second_user) == []
    with pytest.raises(LookupError, match="Stream not found"):
        await service.save_stream(second_user, StreamInput(name="Stolen"), saved.id)
    with pytest.raises(LookupError, match="Stream not found"):
        await service.delete_stream(second_user, saved.id)
    updated = await service.save_stream(first_user, StreamInput(name="Renamed"), saved.id)
    assert updated.id == saved.id
    assert updated.created_at == saved.created_at
    assert (await service.streams(first_user))[0].name == "Renamed"
    async with factory() as session:
        user = await session.get(PlatformUserModel, first_user)
        assert user.metadata_["unrelated_auth_state"] == {"keep": True}
    await service.delete_stream(first_user, saved.id)
    assert await service.streams(first_user) == []


@pytest.mark.asyncio
async def test_fetch_all_schedules_idle_publishers_and_reuses_busy_jobs(persistence):
    from unittest.mock import AsyncMock

    from newsintel.application.sources.service import SourceService
    from newsintel.infrastructure.db.models import DiscoveryChannelModel, FetchJobModel

    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    second_id = uuid7()
    async with factory() as session, session.begin():
        first_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        session.add(PublisherModel(id=second_id, name="Idle source", slug=second_id.hex,
                    canonical_domain=f"{second_id.hex}.example.org", created_at=now, updated_at=now))
        await session.flush()
        for publisher_id in (first_id, second_id):
            session.add(DiscoveryChannelModel(
                id=uuid7(), publisher_id=publisher_id, channel_type="rss",
                endpoint_url=f"https://news.example/{publisher_id}/feed", active=True,
                config={}, strategy_version="test", next_poll_at=now,
                poll_min_seconds=60, poll_max_seconds=3600, current_poll_seconds=300,
                created_at=now, updated_at=now,
            ))
    service = SourceService(session_factory=factory, fetcher=AsyncMock())
    first = await service.create_fetch_job(publisher_id=first_id)
    assert (await service.create_fetch_job(publisher_id=first_id)).id == first.id
    idle = await service.create_fetch_job(publisher_id=None)
    assert idle.id != first.id
    assert idle.publishers_total == 1
    assert "already have a fetch" in idle.message
    reused = await service.create_fetch_job(publisher_id=None)
    assert reused.id in {first.id, idle.id}
    async with factory() as session:
        jobs = (await session.scalars(select(FetchJobModel))).all()
        assert len(jobs) == 2
        scheduled = await session.get(FetchJobModel, idle.id)
        assert scheduled.metadata_["publisher_ids"] == [str(second_id)]


@pytest.mark.asyncio
async def test_background_poll_completion_preserves_new_manual_request(persistence):
    from dataclasses import replace
    from unittest.mock import AsyncMock

    from newsintel.application.acquisition.polling import PollCompletion, PollRunStatus
    from newsintel.application.sources.service import SourceService
    from newsintel.infrastructure.db.models import DiscoveryChannelModel
    from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository

    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    channel_id = uuid7()
    async with factory() as session, session.begin():
        publisher_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        session.add(DiscoveryChannelModel(
            id=channel_id, publisher_id=publisher_id, channel_type="rss",
            endpoint_url="https://news.example/current/feed", active=True,
            config={}, strategy_version="test", next_poll_at=now,
            poll_min_seconds=60, poll_max_seconds=3600, current_poll_seconds=300,
            created_at=now, updated_at=now,
        ))
    repository = SqlAlchemyPollingRepository(factory)
    leased = (await repository.lease_due_channels(worker_id="test", limit=1, lease_seconds=120))[0]
    run = await repository.start_run(channel_id=channel_id, worker_id="test", trace_id=uuid7(),
                                     started_at=now, lease_version=leased.lease_version)
    assert run.fetch_job_id is None
    service = SourceService(session_factory=factory, fetcher=AsyncMock())
    job = await service.create_fetch_job(publisher_id=publisher_id)
    completed_at = datetime.now(UTC)
    completion = PollCompletion(
        run_id=run.id, channel_id=channel_id, trace_id=run.trace_id,
        status=PollRunStatus.NOT_MODIFIED, completed_at=completed_at,
        next_poll_at=completed_at+timedelta(hours=1), current_poll_seconds=3600,
        http_status=304, not_modified=True, worker_id="test", lease_version=run.lease_version,
        fetch_job_id=run.fetch_job_id,
    )
    await repository.complete(completion)
    async with factory() as session:
        channel = await session.get(DiscoveryChannelModel, channel_id)
        assert channel.fetch_job_id == job.id
        assert channel.next_poll_at == completed_at
    leased = (await repository.lease_due_channels(worker_id="test", limit=1, lease_seconds=120))[0]
    run = await repository.start_run(channel_id=channel_id, worker_id="test", trace_id=uuid7(),
                                     started_at=datetime.now(UTC), lease_version=leased.lease_version)
    assert run.fetch_job_id == job.id
    await repository.complete(replace(completion, run_id=run.id, trace_id=run.trace_id,
        lease_version=run.lease_version, fetch_job_id=job.id, completed_at=datetime.now(UTC)))
    async with factory() as session:
        assert (await session.get(DiscoveryChannelModel, channel_id)).fetch_job_id is None
    assert (await service.get_fetch_job(job.id)).status == "completed"


@pytest.mark.asyncio
async def test_poller_prioritizes_live_channels_and_shares_slots_between_publishers(persistence):
    from newsintel.infrastructure.db.models import DiscoveryChannelModel
    from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository

    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    second_id = uuid7()
    async with factory() as session, session.begin():
        first_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        session.add(PublisherModel(id=second_id, name="Second source", slug=second_id.hex,
                    canonical_domain=f"{second_id.hex}.example.org", created_at=now, updated_at=now))
        await session.flush()
        feed_id = uuid7()
        for publisher_id, kind, channel_id in (
            [(first_id, "sitemap", uuid7()) for _ in range(12)]
            + [(first_id, "rss", feed_id), (second_id, "homepage", uuid7())]
        ):
            session.add(DiscoveryChannelModel(
                id=channel_id, publisher_id=publisher_id, channel_type=kind,
                endpoint_url=f"https://news.example/{channel_id}", config={}, strategy_version="test",
                active=True, next_poll_at=now-timedelta(days=30 if kind=="sitemap" else 1),
                poll_min_seconds=60, poll_max_seconds=3600, current_poll_seconds=300,
                created_at=now, updated_at=now,
            ))
    claimed = await SqlAlchemyPollingRepository(factory).lease_due_channels(
        worker_id="regression", limit=2, lease_seconds=120,
    )
    assert {item.publisher_id for item in claimed} == {first_id, second_id}
    assert feed_id in {item.id for item in claimed}


@pytest.mark.asyncio
async def test_article_slots_are_fair_and_disabled_leases_are_paused(persistence):
    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    second_id, disabled_id = uuid7(), uuid7()
    paused_id = uuid7()
    async with factory() as session, session.begin():
        first_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        for key, active in ((second_id, True), (disabled_id, False)):
            session.add(PublisherModel(id=key, name="Queue source", slug=key.hex,
                        canonical_domain=f"{key.hex}.example.org", active=active,
                        created_at=now, updated_at=now))
        await session.flush()
        for publisher_id, article_key in (
            [(first_id, uuid7()) for _ in range(8)] + [(second_id, uuid7()), (disabled_id, paused_id)]
        ):
            url = f"https://news.example/{article_key}"
            session.add(UrlCandidateModel(
                id=article_key, publisher_id=publisher_id, normalized_url=url,
                url_fingerprint=hashlib.sha256(url.encode()).digest(),
                state="leased" if publisher_id==disabled_id else "ready", priority_score=1,
                priority_components={}, priority_policy_version="test", next_fetch_at=now,
                published_at=now-timedelta(minutes=1 if publisher_id==second_id else 0),
                first_discovered_at=now, lease_owner="dead-worker" if publisher_id==disabled_id else None,
                lease_expires_at=now-timedelta(days=3) if publisher_id==disabled_id else None,
                created_at=now, updated_at=now,
            ))
    claimed = await SqlAlchemyArticleProcessingRepository(factory).lease_due_candidates(
        worker_id="regression", limit=2, lease_seconds=120,
    )
    assert {item.publisher_id for item in claimed} == {first_id, second_id}
    async with factory() as session:
        paused = await session.get(UrlCandidateModel, paused_id)
        assert paused.state == paused.processing_stage == "paused"
        assert paused.lease_owner is None
        assert paused.lease_expires_at is None


@pytest.mark.asyncio
async def test_frontier_conflicts_are_idempotent_and_manual_article_budget_is_enforced(persistence):
    from newsintel.application.acquisition.ports import DiscoveryBudgetReached
    from newsintel.domain.acquisition.entities import UrlCandidate
    from newsintel.infrastructure.db.acquisition_repositories import SqlAlchemyFrontierRepository
    from newsintel.infrastructure.db.models import FetchJobModel

    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        existing = await session.get(UrlCandidateModel, candidate_id)
        repository = SqlAlchemyFrontierRepository(session)
        duplicate = UrlCandidate(publisher_id=existing.publisher_id,
                    normalized_url=existing.normalized_url, url_fingerprint=existing.url_fingerprint,
                    priority_score=1, priority_components={}, priority_policy_version="test",
                    next_fetch_at=now)
        assert not await repository.add_candidate(duplicate)
        assert (await repository.get_by_fingerprint(duplicate.url_fingerprint)).id == candidate_id
        job_id = uuid7()
        session.add(FetchJobModel(id=job_id, publisher_id=existing.publisher_id,
                    job_type="publisher", status="running", created_at=now, updated_at=now,
                    metadata_={"max_new_urls": 1, "max_new_urls_per_publisher": 1}))
        await session.flush()
        for number in range(2):
            url = f"https://news.example/new-report-{number}"
            candidate = UrlCandidate(publisher_id=existing.publisher_id, normalized_url=url,
                        url_fingerprint=hashlib.sha256(url.encode()).digest(), priority_score=1,
                        priority_components={}, priority_policy_version="test", next_fetch_at=now,
                        originating_fetch_job_id=job_id)
            if number == 0:
                assert await repository.add_candidate(candidate)
            else:
                with pytest.raises(DiscoveryBudgetReached):
                    await repository.add_candidate(candidate)


@pytest.mark.asyncio
async def test_manual_fetch_is_bounded_and_failed_polls_are_not_reported_as_success(persistence):
    from unittest.mock import AsyncMock

    from newsintel.application.sources.service import SourceService
    from newsintel.infrastructure.db.models import ChannelPollRunModel, DiscoveryChannelModel

    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        publisher_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        for number in range(50):
            session.add(DiscoveryChannelModel(
                id=uuid7(), publisher_id=publisher_id, channel_type="rss" if number==0 else "category",
                endpoint_url=f"https://news.example/current/{number}", active=True,
                config={}, strategy_version="test", next_poll_at=now,
                last_success_at=now-timedelta(hours=1),
                poll_min_seconds=60, poll_max_seconds=3600, current_poll_seconds=300,
                created_at=now, updated_at=now,
            ))
    service = SourceService(session_factory=factory, fetcher=AsyncMock())
    job = await service.create_fetch_job(publisher_id=publisher_id)
    assert job.status == "scheduled"
    async with factory() as session, session.begin():
        linked = list((await session.scalars(select(DiscoveryChannelModel).where(
            DiscoveryChannelModel.fetch_job_id == job.id))).all())
        assert len(linked) == 20
        assert any(row.channel_type == "rss" for row in linked)
        session.add(ChannelPollRunModel(
            id=uuid7(), channel_id=linked[0].id, worker_id="test", status="failed",
            started_at=now, completed_at=now, http_status=403, trace_id=uuid7(), fetch_job_id=job.id,
        ))
        for row in linked:
            row.fetch_job_id = None
    finished = await service.get_fetch_job(job.id)
    assert finished.status == "failed"
    assert finished.completed_at is not None
    view = (await service.list_publishers())[0]
    assert view.last_fetched_at == now-timedelta(hours=1)


@pytest.mark.asyncio
async def test_news_stream_limit_does_not_prevent_editing_existing_stream(persistence):
    factory, _, _ = persistence
    user_id = uuid7()
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        session.add(PlatformUserModel(
            id=user_id, auth_provider="test", auth_provider_user_id=str(user_id),
            access_status="approved", role="viewer", requested_at=now,
            metadata_={}, created_at=now, updated_at=now,
        ))
    service = NewsDigestService(factory)
    for number in range(20):
        saved = await service.save_stream(user_id, StreamInput(name=f"Stream {number}"))
    with pytest.raises(ValueError, match="20 streams"):
        await service.save_stream(user_id, StreamInput(name="One too many"))
    updated = await service.save_stream(user_id, StreamInput(name="Updated at limit"), saved.id)
    assert updated.id == saved.id


@pytest.mark.asyncio
async def test_expired_article_lease_is_recovered_before_newer_candidates(persistence):
    factory, candidate_id, _ = persistence
    now = datetime.now(UTC)
    async with factory() as session, session.begin():
        stale = await session.get(UrlCandidateModel, candidate_id)
        stale.state = "leased"
        stale.lease_owner = "stopped-worker"
        stale.lease_expires_at = now-timedelta(minutes=10)
        stale.published_at = now-timedelta(days=1)
        stale.lease_version = 3
        publisher_id = stale.publisher_id
        for number in range(5):
            url = f"https://news.example/latest/{number}"
            session.add(UrlCandidateModel(
                id=uuid7(), publisher_id=publisher_id, normalized_url=url,
                url_fingerprint=hashlib.sha256(url.encode()).digest(), state="ready",
                priority_score=1, priority_components={}, priority_policy_version="test",
                next_fetch_at=now, published_at=now, first_discovered_at=now,
                created_at=now, updated_at=now,
            ))
    claimed = await SqlAlchemyArticleProcessingRepository(factory).lease_due_candidates(
        worker_id="recovery", limit=1, lease_seconds=120,
    )
    assert claimed[0].id == candidate_id
    assert claimed[0].lease_version == 4
    assert claimed[0].lease_owner == "recovery"


@pytest.mark.asyncio
async def test_busy_week_digest_samples_across_days_and_keeps_quality_metadata(persistence, monkeypatch):
    factory, candidate_id, _ = persistence
    end = datetime.now(UTC)
    async with factory() as session, session.begin():
        publisher_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        event_id = uuid7()
        session.add(EventModel(
            id=event_id, slug=event_id.hex, title="Week sampling regression",
            lifecycle_status="active", assignment_status="provisional",
            first_detected_at=end, last_material_change_at=end, metadata_={},
            created_at=end, updated_at=end,
        ))
        await session.flush()
        for number, day in enumerate([0]*20 + [2, 4, 6]):
            article_id = uuid7()
            url = f"https://week.example/report/{article_id}"
            title = f"National public policy announcement number {number}"
            published = end-timedelta(days=day, minutes=number+1)
            session.add(ArticleModel(
                id=article_id, event_id=event_id, publisher_id=publisher_id,
                canonical_url=url, normalized_url_hash=hashlib.sha256(url.encode()).digest(),
                title=title, language="en", published_at=published,
                first_observed_at=end-timedelta(minutes=1),
                created_at=end-timedelta(minutes=1), updated_at=end,
            ))
            await session.flush()
            session.add(ArticleVersionModel(
                id=uuid7(), article_id=article_id, version_number=1, source_url=url, final_url=url,
                title=title, byline=None, language="en", published_at=published,
                retrieved_at=end-timedelta(seconds=30),
                content_sha256=hashlib.sha256(str(article_id).encode()).hexdigest(),
                text_content=f"Officials said policy number {number} will fund local transport improvements next year.",
                extraction_method="test", extraction_warnings=[],
                metadata_={"extraction_quality_score": .9}, created_at=end-timedelta(seconds=30),
            ))
    monkeypatch.setattr("newsintel.application.digests.MAX_REPORTS", 4)
    service = NewsDigestService(factory)
    weekly = await service.edition(DigestRequest(period="weekly", full_stream=True, as_of=end))
    assert weekly.eligible_reports == 23
    assert weekly.scanned_reports == 4
    assert weekly.sampled
    assert weekly.selected_days == 4
    assert weekly.selected_publisher_count == 1
    assert all(item.summary_available for item in weekly.items)
    daily = await service.edition(DigestRequest(full_stream=True, as_of=end))
    assert daily.eligible_reports == 20
    assert daily.selected_days == 1


@pytest.mark.asyncio
async def test_pdf_page_provenance_survives_storage_and_article_api(persistence):
    """Persist source-page offsets and expose them from the same article-version API."""
    from newsintel.application.articles.query_service import ArticleQueryService

    factory, _, _ = persistence
    repository = SqlAlchemyArticleProcessingRepository(factory)
    candidate, = await repository.lease_due_candidates(
        worker_id="pdf-page-test", limit=1, lease_seconds=120,
    )
    now = datetime.now(UTC)
    run = await repository.start_fetch(
        candidate_id=candidate.id, worker_id="pdf-page-test",
        trace_id=uuid4(), started_at=now, lease_version=candidate.lease_version,
    )
    url = candidate.normalized_url
    pdf_bytes = b"%PDF-1.4\n%%EOF\n"
    text = "The ministry announced a new inspection report and released its evidence."
    pages = [{
        "page": 1, "source_url": url + "#page=1",
        "char_start": 0, "char_end": len(text),
        "extraction_method": "pdf_native_text",
        "ocr_unverified": False,
    }]
    extracted = ExtractedArticle(
        title="Inspection report", byline=None,
        published_at=now, modified_at=None, language=None,
        canonical_url=url, text_content=text, content_sha256="e" * 64,
        extraction_method="pdf_native_pages", metadata={
            "document_type": "application/pdf",
            "document_page_count": 1,
            "document_pages_processed": 1,
            "document_truncated": False,
            "document_pages": pages,
            "extraction_quality_score": 0.8,
            "word_count": len(text.split()),
        }, warnings=(),
    )
    fetched = FetchResult(
        requested_url=url, final_url=url, status_code=200,
        headers={"content-type": "application/pdf"}, body=pdf_bytes,
        body_sha256="f" * 64, retrieved_at=now, redirect_chain=(),
    )
    result = await repository.complete_success(
        candidate=candidate, run=run, fetched=fetched,
        extracted=extracted, raw_artifact=None, completed_at=now,
    )
    detail = await ArticleQueryService(factory).get_article(result.article_id)
    assert detail is not None and detail.latest_version is not None
    assert detail.latest_version.document_page_count == 1
    assert detail.latest_version.document_pages == pages
    assert detail.latest_version.text_content == text
