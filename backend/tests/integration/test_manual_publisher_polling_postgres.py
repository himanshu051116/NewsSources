"""Manual publisher checks are one-shot, including newly discovered child channels."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from test_article_repository_postgres import persistence as _persistence_fixture

from newsintel.application.acquisition.polling import PollCompletion, PollRunStatus
from newsintel.application.sources.service import SourceService
from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.models import (
    ChannelPollRunModel,
    DiscoveryChannelModel,
    OutboxEventModel,
    PublisherModel,
    UrlCandidateModel,
)
from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository

pytestmark = pytest.mark.integration
persistence = _persistence_fixture


async def add_channel(factory, candidate_id, frequency):
    now = datetime.now(UTC)
    channel_id = uuid7()
    async with factory() as session, session.begin():
        publisher_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        publisher = await session.get(PublisherModel, publisher_id)
        publisher.fetch_frequency = frequency
        session.add(DiscoveryChannelModel(
            id=channel_id, publisher_id=publisher_id, channel_type="rss",
            endpoint_url="https://news.example/current/feed", active=True,
            config={}, strategy_version="test", next_poll_at=now,
            poll_min_seconds=3600, poll_max_seconds=3600, current_poll_seconds=3600,
            created_at=now, updated_at=now,
        ))
    return channel_id, publisher_id


async def finish_check(repository, channel_id, *, status=PollRunStatus.SUCCEEDED,
                       before_completion=None):
    channel, = await repository.lease_due_channels(worker_id="test", limit=1, lease_seconds=120)
    assert channel.id == channel_id
    run = await repository.start_run(channel_id=channel_id, worker_id="test", trace_id=uuid7(),
                                    started_at=datetime.now(UTC), lease_version=channel.lease_version)
    if before_completion is not None:
        await before_completion()
    completed_at = datetime.now(UTC)
    completion = PollCompletion(
        run_id=run.id, channel_id=channel_id, trace_id=run.trace_id, status=status,
        completed_at=completed_at, next_poll_at=completed_at + timedelta(hours=1),
        current_poll_seconds=3600, worker_id="test", lease_version=run.lease_version,
        fetch_job_id=run.fetch_job_id,
    )
    await repository.complete(completion)
    return completion


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(PollRunStatus)[1:])
async def test_manual_publisher_completion_does_not_enable_automatic_polling(persistence, status):
    factory, candidate_id, _ = persistence
    channel_id, _ = await add_channel(factory, candidate_id, "manual")
    repository = SqlAlchemyPollingRepository(factory)
    await finish_check(repository, channel_id, status=status)
    async with factory() as session:
        channel = await session.get(DiscoveryChannelModel, channel_id)
        assert channel.next_poll_at is None
        event = await session.scalar(select(OutboxEventModel).where(
            OutboxEventModel.aggregate_id == channel_id))
        assert event.payload["next_poll_at"] is None
    assert not await repository.lease_due_channels(worker_id="test", limit=1, lease_seconds=120)
    # Explicit channel scheduling remains available without requiring a publisher job.
    assert await repository.schedule_now(channel_id)
    await finish_check(repository, channel_id)


@pytest.mark.asyncio
async def test_manual_publisher_preserves_a_new_fetch_requested_during_poll(persistence):
    factory, candidate_id, _ = persistence
    channel_id, publisher_id = await add_channel(factory, candidate_id, "manual")
    repository = SqlAlchemyPollingRepository(factory)
    service = SourceService(session_factory=factory, fetcher=AsyncMock())

    async def request_new_fetch():
        await service.create_fetch_job(publisher_id=publisher_id)

    completion = await finish_check(repository, channel_id, before_completion=request_new_fetch)
    async with factory() as session:
        channel = await session.get(DiscoveryChannelModel, channel_id)
        assert channel.fetch_job_id is not None
        assert channel.next_poll_at == completion.completed_at
    await finish_check(repository, channel_id)
    async with factory() as session:
        channel = await session.get(DiscoveryChannelModel, channel_id)
        assert channel.fetch_job_id is None
        assert channel.next_poll_at is None


@pytest.mark.asyncio
async def test_automatic_publisher_keeps_its_next_poll(persistence):
    factory, candidate_id, _ = persistence
    channel_id, _ = await add_channel(factory, candidate_id, "hourly")
    repository = SqlAlchemyPollingRepository(factory)
    completion = await finish_check(repository, channel_id)
    async with factory() as session:
        channel = await session.get(DiscoveryChannelModel, channel_id)
        assert channel.next_poll_at == completion.next_poll_at


@pytest.mark.asyncio
async def test_source_health_uses_the_publishers_manual_frequency(persistence):
    factory, candidate_id, _ = persistence
    channel_id, publisher_id = await add_channel(factory, candidate_id, "manual")
    last_success = datetime.now(UTC) - timedelta(hours=12)
    async with factory() as session, session.begin():
        channel = await session.get(DiscoveryChannelModel, channel_id)
        channel.last_success_at = last_success
        channel.current_poll_seconds = 300
        session.add(ChannelPollRunModel(
            id=uuid7(), channel_id=channel_id, worker_id="test", status="succeeded",
            started_at=last_success, completed_at=last_success, trace_id=uuid7(),
            discovered_count=10, admitted_count=10, observation_count=10,
        ))
    service = SourceService(session_factory=factory, fetcher=AsyncMock())
    health = await service.source_health(publisher_id)
    assert health.channels[0].health_status == "healthy"
    assert health.channels[0].recency == 0.0
    async with factory() as session, session.begin():
        (await session.get(PublisherModel, publisher_id)).fetch_frequency = "every_15_minutes"
    health = await service.source_health(publisher_id)
    assert health.channels[0].health_status == "degraded"
