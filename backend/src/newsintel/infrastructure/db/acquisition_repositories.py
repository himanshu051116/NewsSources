from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from newsintel.application.acquisition.ports import (
    ChannelRepository,
    DiscoveryBudgetReached,
    FrontierRepository,
    OutboxRepository,
    PublisherRepository,
)
from newsintel.contracts.events import IntegrationEvent
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.entities import (
    DiscoveryChannel,
    Publisher,
    UrlCandidate,
    UrlDiscovery,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType
from newsintel.infrastructure.db.models import (
    ArticleModel,
    DiscoveryChannelModel,
    FetchJobModel,
    FetchJobObservationModel,
    OutboxEventModel,
    PublisherModel,
    UrlCandidateModel,
    UrlDiscoveryModel,
)


def _publisher_from_model(row: PublisherModel) -> Publisher:
    return Publisher(
        id=row.id,
        name=row.name,
        slug=row.slug,
        canonical_domain=row.canonical_domain,
        active=row.active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _channel_from_model(row: DiscoveryChannelModel) -> DiscoveryChannel:
    return DiscoveryChannel(
        id=row.id,
        publisher_id=row.publisher_id,
        channel_type=DiscoveryChannelType(row.channel_type),
        endpoint_url=row.endpoint_url,
        strategy_version=row.strategy_version,
        config=row.config,
        active=row.active,
        next_poll_at=row.next_poll_at,
        poll_min_seconds=row.poll_min_seconds,
        poll_max_seconds=row.poll_max_seconds,
        current_poll_seconds=row.current_poll_seconds,
        etag=row.etag,
        last_modified=row.last_modified,
        last_polled_at=row.last_polled_at,
        last_success_at=row.last_success_at,
        lease_owner=row.lease_owner,
        lease_version=row.lease_version,
        lease_heartbeat_at=row.lease_heartbeat_at,
        lease_expires_at=row.lease_expires_at,
        fetch_job_id=row.fetch_job_id,
        consecutive_failures=row.consecutive_failures,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _candidate_from_model(row: UrlCandidateModel) -> UrlCandidate:
    return UrlCandidate(
        id=row.id,
        publisher_id=row.publisher_id,
        normalized_url=row.normalized_url,
        url_fingerprint=row.url_fingerprint,
        state=row.state,
        priority_score=row.priority_score,
        priority_components=row.priority_components,
        priority_policy_version=row.priority_policy_version,
        next_fetch_at=row.next_fetch_at,
        published_at=row.published_at,
        first_discovered_at=row.first_discovered_at,
        attempt_count=row.attempt_count,
        url_type=row.url_type,
        originating_fetch_job_id=row.originating_fetch_job_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyPublisherRepository(PublisherRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, publisher_id: UUID) -> Publisher | None:
        row = await self._session.get(PublisherModel, publisher_id)
        return _publisher_from_model(row) if row else None

    async def get_by_slug(self, slug: str) -> Publisher | None:
        row = await self._session.scalar(
            select(PublisherModel).where(PublisherModel.slug == slug)
        )
        return _publisher_from_model(row) if row else None

    async def add(self, publisher: Publisher) -> None:
        self._session.add(
            PublisherModel(
                id=publisher.id,
                name=publisher.name,
                slug=publisher.slug,
                canonical_domain=publisher.canonical_domain,
                active=publisher.active,
                created_at=publisher.created_at,
                updated_at=publisher.updated_at,
            )
        )


class SqlAlchemyChannelRepository(ChannelRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, channel_id: UUID) -> DiscoveryChannel | None:
        row = await self._session.get(DiscoveryChannelModel, channel_id)
        return _channel_from_model(row) if row else None

    async def get_by_endpoint(
        self,
        publisher_id: UUID,
        endpoint_url: str,
    ) -> DiscoveryChannel | None:
        row = await self._session.scalar(
            select(DiscoveryChannelModel).where(
                DiscoveryChannelModel.publisher_id == publisher_id,
                DiscoveryChannelModel.endpoint_url == endpoint_url,
            )
        )
        return _channel_from_model(row) if row else None

    async def add(self, channel: DiscoveryChannel) -> bool:
        created_id = await self._session.scalar(
            insert(DiscoveryChannelModel).values(
                id=channel.id,
                publisher_id=channel.publisher_id,
                channel_type=channel.channel_type.value,
                endpoint_url=channel.endpoint_url,
                config=channel.config,
                strategy_version=channel.strategy_version,
                active=channel.active,
                next_poll_at=channel.next_poll_at,
                poll_min_seconds=channel.poll_min_seconds,
                poll_max_seconds=channel.poll_max_seconds,
                current_poll_seconds=channel.current_poll_seconds,
                etag=channel.etag,
                last_modified=channel.last_modified,
                last_polled_at=channel.last_polled_at,
                last_success_at=channel.last_success_at,
                lease_owner=channel.lease_owner,
                lease_version=channel.lease_version,
                lease_heartbeat_at=channel.lease_heartbeat_at,
                lease_expires_at=channel.lease_expires_at,
                fetch_job_id=channel.fetch_job_id,
                consecutive_failures=channel.consecutive_failures,
                created_at=channel.created_at,
                updated_at=channel.updated_at,
            ).on_conflict_do_nothing(index_elements=[
                DiscoveryChannelModel.publisher_id, DiscoveryChannelModel.endpoint_url,
            ]).returning(DiscoveryChannelModel.id)
        )
        return created_id is not None


class SqlAlchemyFrontierRepository(FrontierRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_fingerprint(self, fingerprint: bytes) -> UrlCandidate | None:
        row = await self._session.scalar(
            select(UrlCandidateModel).where(
                UrlCandidateModel.url_fingerprint == fingerprint
            )
        )
        return _candidate_from_model(row) if row else None

    async def add_candidate(self, candidate: UrlCandidate) -> bool:
        if candidate.originating_fetch_job_id is not None:
            job = await self._session.get(FetchJobModel, candidate.originating_fetch_job_id,
                                          with_for_update=True)
            if job is not None:
                total, publisher_total = (await self._session.execute(select(
                    func.count(UrlCandidateModel.id),
                    func.count(UrlCandidateModel.id).filter(
                        UrlCandidateModel.publisher_id == candidate.publisher_id),
                ).where(UrlCandidateModel.originating_fetch_job_id == job.id,
                        UrlCandidateModel.created_at >= job.created_at))).one()
                if (total >= int(job.metadata_.get("max_new_urls", 2000))
                        or publisher_total >= int(job.metadata_.get("max_new_urls_per_publisher", 300))):
                    raise DiscoveryBudgetReached("Manual fetch new-article limit reached")
        created_id = await self._session.scalar(
            insert(UrlCandidateModel).values(
                id=candidate.id,
                publisher_id=candidate.publisher_id,
                normalized_url=candidate.normalized_url,
                url_fingerprint=candidate.url_fingerprint,
                state=candidate.state,
                priority_score=candidate.priority_score,
                priority_components=candidate.priority_components,
                priority_policy_version=candidate.priority_policy_version,
                next_fetch_at=candidate.next_fetch_at,
                published_at=candidate.published_at,
                first_discovered_at=candidate.first_discovered_at,
                url_type=candidate.url_type,
                originating_fetch_job_id=candidate.originating_fetch_job_id,
                attempt_count=candidate.attempt_count,
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            ).on_conflict_do_nothing(index_elements=[UrlCandidateModel.url_fingerprint])
             .returning(UrlCandidateModel.id)
        )
        return created_id is not None

    async def update_candidate_job_metadata(
        self,
        *,
        candidate_id: UUID,
        published_at: datetime | None,
        discovered_at: datetime,
        url_type: str | None = None,
        fetch_job_id: UUID | None = None,
    ) -> UrlCandidate | None:
        row = await self._session.get(UrlCandidateModel, candidate_id, with_for_update=True)
        if row is None:
            return None

        changed = False
        normalized_discovered_at = _normalize_datetime(discovered_at)
        if row.first_discovered_at is None:
            row.first_discovered_at = normalized_discovered_at
            changed = True
        else:
            row.first_discovered_at = min(
                _normalize_datetime(row.first_discovered_at),
                normalized_discovered_at,
            )
            changed = True

        normalized_published_at = (
            _normalize_datetime(published_at) if published_at is not None else None
        )
        if normalized_published_at is not None and (
            row.published_at is None
            or normalized_published_at > _normalize_datetime(row.published_at)
        ):
            row.published_at = normalized_published_at
            changed = True

        if url_type and row.url_type != url_type:
            row.url_type = url_type
            changed = True
        if fetch_job_id is not None and row.originating_fetch_job_id is None:
            row.originating_fetch_job_id = fetch_job_id
            changed = True

        # A recent report can be corrected without changing its URL or headline.
        # Rediscovery permits one recheck per day; it never steals an active lease
        # or revives rejected/permanently failed URLs or old archive material.
        now = datetime.now(UTC)
        article_published = None
        if row.state == "processed" and row.article_id is not None and row.last_fetch_at is not None \
                and _normalize_datetime(row.last_fetch_at) <= now - timedelta(hours=24):
            article_published = await self._session.scalar(select(ArticleModel.published_at).where(
                ArticleModel.id == row.article_id))
        if article_published is not None \
                and now - timedelta(days=7) <= _normalize_datetime(article_published) <= now:
            row.state = "ready"
            row.processing_stage = "queued"
            row.next_fetch_at = now
            row.attempt_count = 0
            row.processing_started_at = None
            row.processing_completed_at = None
            row.processing_duration_ms = None
            row.stage_timestamps = {}
            row.last_error = row.last_failure_code = row.last_failure_message = None
            changed = True

        if changed:
            row.updated_at = datetime.now(UTC)
            await self._session.flush()
        return _candidate_from_model(row)

    async def add_discovery_if_absent(self, discovery: UrlDiscovery) -> bool:
        statement = (
            insert(UrlDiscoveryModel)
            .values(
                id=discovery.id,
                url_candidate_id=discovery.url_candidate_id,
                channel_id=discovery.channel_id,
                discovered_url=discovery.discovered_url,
                discovered_at=discovery.discovered_at,
                channel_position=discovery.channel_position,
                payload_hash=discovery.payload_hash,
                fetch_job_id=discovery.fetch_job_id,
            )
            .on_conflict_do_nothing(
                constraint="uq_url_discoveries_candidate_channel",
            )
            .returning(UrlDiscoveryModel.id)
        )
        return await self._session.scalar(statement) is not None

    async def add_fetch_job_observation(
        self,
        *,
        fetch_job_id: UUID,
        candidate_id: UUID,
        channel_id: UUID,
        candidate_created: bool,
        observed_at: datetime,
    ) -> None:
        await self._session.execute(
            insert(FetchJobObservationModel)
            .values(
                id=uuid7(),
                fetch_job_id=fetch_job_id,
                candidate_id=candidate_id,
                channel_id=channel_id,
                candidate_created=candidate_created,
                observed_at=observed_at,
            )
            .on_conflict_do_update(
                constraint="uq_fetch_job_observation",
                set_={
                    "candidate_created": FetchJobObservationModel.candidate_created | candidate_created,
                    "observed_at": observed_at,
                },
            )
        )



def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SqlAlchemyOutboxRepository(OutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: IntegrationEvent) -> None:
        statement = (
            insert(OutboxEventModel)
            .values(
                id=event.event_id,
                event_type=event.event_type,
                event_version=event.event_version,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=event.payload,
                occurred_at=event.occurred_at,
                producer=event.producer,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                traceparent=event.traceparent,
                idempotency_key=event.idempotency_key,
            )
            .on_conflict_do_nothing(
                constraint="uq_outbox_events_idempotency_key",
            )
        )
        await self._session.execute(statement)
