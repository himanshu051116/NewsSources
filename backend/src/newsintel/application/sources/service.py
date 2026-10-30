from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy import case, distinct, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.collectors.source_discovery import (
    DiscoveredEndpoint,
    ValidatedEndpoint,
    canonical_domain,
    common_discovery_endpoints,
    discover_alternate_links,
    discover_http_link_endpoints,
    discover_listing_endpoints,
    discover_robot_sitemaps,
    discover_syndication_directory_endpoints,
    normalize_homepage_url,
    origin_for_url,
    unique_endpoints,
    validate_endpoint_payload,
)
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.contracts.events import IntegrationEvent
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.canonicalization import (
    CanonicalizationPolicy,
    canonicalize_url,
)
from newsintel.domain.acquisition.models import DiscoveryChannelType
from newsintel.domain.acquisition.policies import normalize_domain
from newsintel.domain.acquisition.scheduling import (
    CHANNEL_PRIORITY,
    MAX_MANUAL_CHANNELS_PER_PUBLISHER,
    current_sitemap,
)
from newsintel.infrastructure.db.acquisition_maintenance import pause_disabled_candidates
from newsintel.infrastructure.db.models import (
    ArticleModel,
    ChannelPollRunModel,
    DiscoveryChannelModel,
    FetchJobModel,
    FetchJobObservationModel,
    OutboxEventModel,
    PublisherDomainModel,
    PublisherExtractionProfileModel,
    PublisherModel,
    RobotsSnapshotModel,
    SourceCandidateModel,
    UrlCandidateModel,
    UrlDiscoveryModel,
)

from .audit import DiscoveryObservationRecord, calculate_discovery_audit
from .dto import (
    ChannelDiscoveryAuditView,
    ChannelSourceHealthView,
    DiscoveredChannelView,
    DiscoverPublisherCommand,
    FetchFrequency,
    FetchJobView,
    PublisherDiscoveryAuditView,
    PublisherDiscoveryResult,
    PublisherExtractionProfileView,
    PublisherSourceHealthView,
    PublisherSourceView,
    SourceCandidateView,
    UpdatePublisherExtractionProfileCommand,
)
from .health import ChannelHealthInputs, calculate_channel_health

DISCOVERY_STRATEGY_VERSION = "source-fabric-discovery-v2"
logger = structlog.get_logger(__name__)


class SourceDiscoveryError(RuntimeError):
    pass


class PublisherConflictError(ValueError):
    pass


class PublisherNotFoundError(LookupError):
    pass


class Fetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...


@dataclass(frozen=True, slots=True)
class FrequencyPolicy:
    next_poll_at: datetime | None
    poll_min_seconds: int
    poll_max_seconds: int
    current_poll_seconds: int


class SourceService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        fetcher: Fetcher,
        max_new_urls_per_publisher_fetch: int = 300,
        max_new_urls_per_fetch_job: int = 2000,
    ) -> None:
        self._session_factory = session_factory
        self._fetcher = fetcher
        self._publisher_fetch_limit = max_new_urls_per_publisher_fetch
        self._job_fetch_limit = max_new_urls_per_fetch_job

    async def discover_publisher(
        self,
        command: DiscoverPublisherCommand,
    ) -> PublisherDiscoveryResult:
        now = datetime.now(UTC)
        homepage_url = normalize_homepage_url(command.website_url)
        domain = normalize_domain(canonical_domain(homepage_url))
        slug = _slugify(command.publisher_name)
        homepage = await self._fetcher.fetch(FetchRequest(url=homepage_url))
        if homepage.status_code < 200 or homepage.status_code >= 300:
            raise SourceDiscoveryError(
                f"homepage returned HTTP {homepage.status_code}"
            )

        endpoints: list[DiscoveredEndpoint] = []
        endpoints.append(
            DiscoveredEndpoint(
                url=homepage.final_url,
                source="homepage",
                hinted_type=DiscoveryChannelType.HOMEPAGE,
            )
        )
        endpoints.extend(
            discover_alternate_links(homepage.body, homepage_url=homepage.final_url)
        )
        endpoints.extend(
            discover_http_link_endpoints(homepage.headers, base_url=homepage.final_url)
        )
        endpoints.extend(
            discover_listing_endpoints(homepage.body, homepage_url=homepage.final_url)
        )

        robots_url = f"{origin_for_url(homepage.final_url)}/robots.txt"
        robots_result: FetchResult | None = None
        robots_error: str | None = None
        try:
            robots_result = await self._fetcher.fetch(FetchRequest(url=robots_url))
            if 200 <= robots_result.status_code < 300:
                endpoints.extend(
                    discover_robot_sitemaps(
                        robots_result.body,
                        homepage_url=homepage.final_url,
                    )
                )
        except Exception as exc:
            robots_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            logger.debug(
                "robots_txt_discovery_failed",
                homepage_url=homepage.final_url,
                error_type=type(exc).__name__,
            )

        endpoints.extend(common_discovery_endpoints(homepage.final_url))
        endpoints.extend(
            DiscoveredEndpoint(url=item, source="manual_fallback")
            for item in command.manual_endpoints
        )
        unique = unique_endpoints(tuple(endpoints))
        validated = await self._validate_endpoints(unique)

        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(PublisherModel).where(PublisherModel.canonical_domain == domain)
            )
            if existing is not None:
                raise PublisherConflictError(
                    f"publisher already exists for domain: {domain}"
                )

            publisher = PublisherModel(
                id=uuid7(),
                name=command.publisher_name,
                slug=await _unique_slug(session, slug),
                canonical_domain=domain,
                homepage_url=homepage_url,
                fetch_frequency=command.fetch_frequency.value,
                discovery_status="ready" if validated else "no_channels_found",
                discovery_message=(
                    None
                    if validated
                    else (
                        "No valid RSS, Atom, JSON Feed, sitemap, homepage, or listing-page "
                        "endpoint was discovered. Add a manual endpoint."
                    )
                ),
                active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(publisher)
            await session.flush()

            publisher_domain = PublisherDomainModel(
                id=uuid7(),
                publisher_id=publisher.id,
                domain=domain,
                homepage_url=homepage.final_url,
                is_primary=True,
                active=True,
                discovered_via="publisher_onboarding",
                metadata_={
                    "input_homepage_url": homepage_url,
                    "final_homepage_url": homepage.final_url,
                },
                created_at=now,
                updated_at=now,
            )
            session.add(publisher_domain)
            await session.flush()

            if robots_result is not None or robots_error is not None:
                robots_status = robots_result.status_code if robots_result is not None else None
                robots_body = robots_result.body if robots_result is not None else b""
                if robots_status is not None and 200 <= robots_status < 300:
                    policy_state = "parsed"
                elif robots_status is not None and 400 <= robots_status < 500:
                    policy_state = "missing"
                else:
                    policy_state = "unavailable"
                session.add(
                    RobotsSnapshotModel(
                        id=uuid7(),
                        publisher_domain_id=publisher_domain.id,
                        robots_url=robots_url,
                        fetched_at=(
                            robots_result.retrieved_at
                            if robots_result is not None
                            else now
                        ),
                        expires_at=now + timedelta(hours=1),
                        http_status=robots_status,
                        body_sha256=(
                            robots_result.body_sha256
                            if robots_result is not None and robots_result.body
                            else None
                        ),
                        body_text=(
                            robots_body.decode("utf-8", errors="replace")
                            if robots_body and len(robots_body) <= 1_000_000
                            else None
                        ),
                        policy_state=policy_state,
                        metadata_={
                            "fetch_error": robots_error,
                            "body_truncated": len(robots_body) > 1_000_000,
                        },
                    )
                )

            channels: list[DiscoveredChannelView] = []
            for endpoint in validated:
                created, channel_id = await _create_channel_if_absent(
                    session,
                    publisher_id=publisher.id,
                    endpoint=endpoint,
                    frequency=command.fetch_frequency,
                    now=now,
                )
                channels.append(
                    DiscoveredChannelView(
                        id=channel_id,
                        endpoint_url=endpoint.url,
                        channel_type=endpoint.channel_type.value,
                        source=endpoint.source,
                        item_count=endpoint.item_count,
                        created=created,
                    )
                )

            await _add_outbox(
                session,
                IntegrationEvent(
                    event_type="publisher.source_discovered",
                    aggregate_type="publisher",
                    aggregate_id=publisher.id,
                    payload={
                        "publisher_id": str(publisher.id),
                        "homepage_url": homepage_url,
                        "attempted_endpoint_count": len(unique),
                        "valid_endpoint_count": len(validated),
                        "fetch_frequency": command.fetch_frequency.value,
                    },
                    producer="source-api",
                    idempotency_key=f"publisher.source_discovered:{publisher.id}",
                ),
            )

            source_view = await _publisher_source_view(session, publisher)
            return PublisherDiscoveryResult(
                publisher=source_view,
                channels=channels,
                attempted_endpoint_count=len(unique),
                valid_endpoint_count=len(validated),
                invalid_endpoint_count=max(0, len(unique) - len(validated)),
                manual_fallback_available=not validated,
            )

    async def list_publishers(self) -> list[PublisherSourceView]:
        async with self._session_factory() as session:
            publishers = (
                await session.scalars(
                    select(PublisherModel)
                    .where(PublisherModel.active.is_(True))
                    .order_by(PublisherModel.name)
                )
            ).all()
            return [
                await _publisher_source_view(session, publisher)
                for publisher in publishers
            ]

    async def source_health(
        self,
        publisher_id: UUID,
        *,
        window_hours: int = 24,
    ) -> PublisherSourceHealthView:
        generated_at = datetime.now(UTC)
        since = generated_at - timedelta(hours=window_hours)
        async with self._session_factory() as session:
            publisher = await session.get(PublisherModel, publisher_id)
            if publisher is None or not publisher.active:
                raise PublisherNotFoundError(f"publisher not found: {publisher_id}")
            channels = (
                await session.scalars(
                    select(DiscoveryChannelModel)
                    .where(
                        DiscoveryChannelModel.publisher_id == publisher_id,
                        DiscoveryChannelModel.active.is_(True),
                    )
                    .order_by(
                        DiscoveryChannelModel.channel_type,
                        DiscoveryChannelModel.endpoint_url,
                    )
                )
            ).all()
            channel_ids = [item.id for item in channels]
            runs_by_channel: dict[UUID, list[ChannelPollRunModel]] = {
                item.id: [] for item in channels
            }
            if channel_ids:
                runs = (
                    await session.scalars(
                        select(ChannelPollRunModel).where(
                            ChannelPollRunModel.channel_id.in_(channel_ids),
                            ChannelPollRunModel.started_at >= since,
                        )
                    )
                ).all()
                for run in runs:
                    runs_by_channel.setdefault(run.channel_id, []).append(run)

            views: list[ChannelSourceHealthView] = []
            for channel in channels:
                runs = runs_by_channel.get(channel.id, [])
                successful = sum(1 for run in runs if run.status == "succeeded")
                not_modified = sum(1 for run in runs if run.status == "not_modified")
                failures = sum(1 for run in runs if run.status == "failed")
                health = calculate_channel_health(
                    ChannelHealthInputs(
                        poll_count=len(runs),
                        successful_poll_count=successful,
                        not_modified_count=not_modified,
                        failure_count=failures,
                        discovered_count=sum(run.discovered_count for run in runs),
                        admitted_count=sum(run.admitted_count for run in runs),
                        observation_count=sum(run.observation_count for run in runs),
                        consecutive_failures=channel.consecutive_failures,
                        last_success_at=channel.last_success_at,
                        current_poll_seconds=channel.current_poll_seconds,
                        automatic_polling=publisher.fetch_frequency != FetchFrequency.MANUAL.value,
                    ),
                    now=generated_at,
                )
                views.append(
                    ChannelSourceHealthView(
                        channel_id=channel.id,
                        channel_type=channel.channel_type,
                        endpoint_url=channel.endpoint_url,
                        poll_count=len(runs),
                        successful_poll_count=successful,
                        not_modified_count=not_modified,
                        failure_count=failures,
                        discovered_count=sum(run.discovered_count for run in runs),
                        admitted_count=sum(run.admitted_count for run in runs),
                        observation_count=sum(run.observation_count for run in runs),
                        consecutive_failures=channel.consecutive_failures,
                        last_polled_at=channel.last_polled_at,
                        last_success_at=channel.last_success_at,
                        current_poll_seconds=channel.current_poll_seconds,
                        health_score=health.score,
                        availability=health.availability,
                        observation_yield=health.observation_yield,
                        recency=health.recency,
                        health_status=health.status,
                        health_policy_version=health.policy_version,
                    )
                )
            return PublisherSourceHealthView(
                publisher_id=publisher_id,
                window_hours=window_hours,
                generated_at=generated_at,
                channel_count=len(views),
                healthy_channel_count=sum(item.health_status == "healthy" for item in views),
                watch_channel_count=sum(item.health_status == "watch" for item in views),
                degraded_channel_count=sum(item.health_status == "degraded" for item in views),
                channels=views,
            )

    async def discovery_audit(
        self,
        publisher_id: UUID,
        *,
        window_hours: int = 24,
    ) -> PublisherDiscoveryAuditView:
        generated_at = datetime.now(UTC)
        since = generated_at - timedelta(hours=window_hours)
        async with self._session_factory() as session:
            publisher = await session.get(PublisherModel, publisher_id)
            if publisher is None or not publisher.active:
                raise PublisherNotFoundError(f"publisher not found: {publisher_id}")
            channels = (
                await session.scalars(
                    select(DiscoveryChannelModel).where(
                        DiscoveryChannelModel.publisher_id == publisher_id,
                        DiscoveryChannelModel.active.is_(True),
                    )
                )
            ).all()
            channel_ids = [item.id for item in channels]
            observations: list[DiscoveryObservationRecord] = []
            if channel_ids:
                rows = (
                    await session.execute(
                        select(
                            UrlDiscoveryModel.url_candidate_id,
                            UrlDiscoveryModel.channel_id,
                            UrlDiscoveryModel.discovered_at,
                        ).where(
                            UrlDiscoveryModel.channel_id.in_(channel_ids),
                            UrlDiscoveryModel.discovered_at >= since,
                        )
                    )
                ).all()
                observations = [
                    DiscoveryObservationRecord(
                        candidate_id=row[0],
                        channel_id=row[1],
                        discovered_at=row[2],
                    )
                    for row in rows
                ]
            audit = calculate_discovery_audit(observations, channel_ids=channel_ids)
            channel_by_id = {item.id: item for item in channels}
            return PublisherDiscoveryAuditView(
                publisher_id=publisher_id,
                window_hours=window_hours,
                generated_at=generated_at,
                total_candidates=audit.total_candidates,
                single_channel_candidates=audit.single_channel_candidates,
                multi_channel_candidates=audit.multi_channel_candidates,
                channels=[
                    ChannelDiscoveryAuditView(
                        channel_id=item.channel_id,
                        channel_type=channel_by_id[item.channel_id].channel_type,
                        endpoint_url=channel_by_id[item.channel_id].endpoint_url,
                        observed_candidates=item.observed_candidates,
                        unique_candidates=item.unique_candidates,
                        overlap_candidates=item.overlap_candidates,
                        first_discovery_wins=item.first_discovery_wins,
                        unique_contribution_rate=item.unique_contribution_rate,
                        first_discovery_rate=item.first_discovery_rate,
                    )
                    for item in audit.channels
                ],
            )

    async def list_source_candidates(
        self,
        *,
        state: str = "quarantined",
        limit: int = 100,
    ) -> list[SourceCandidateView]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(SourceCandidateModel)
                    .where(SourceCandidateModel.state == state)
                    .order_by(
                        SourceCandidateModel.score.desc(),
                        SourceCandidateModel.last_seen_at.desc(),
                    )
                    .limit(limit)
                )
            ).all()
            return [
                SourceCandidateView(
                    id=row.id,
                    candidate_url=row.candidate_url,
                    candidate_domain=row.candidate_domain,
                    evidence_type=row.evidence_type,
                    evidence_count=row.evidence_count,
                    score=row.score,
                    state=row.state,
                    first_seen_at=row.first_seen_at,
                    last_seen_at=row.last_seen_at,
                    discovered_from_publisher_id=row.discovered_from_publisher_id,
                )
                for row in rows
            ]

    async def create_fetch_job(
        self,
        *,
        publisher_id: UUID | None,
    ) -> FetchJobView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            publisher_ids = await _fetch_target_publishers(session, publisher_id)
            if publisher_id is not None and not publisher_ids:
                raise PublisherNotFoundError(f"publisher not found: {publisher_id}")
            if not publisher_ids:
                raise PublisherNotFoundError("no active publishers are configured")
            # Serialize manual starts without locking publisher rows against the poller.
            for target in sorted(publisher_ids, key=str):
                await session.execute(select(func.pg_advisory_xact_lock(
                    func.hashtextextended("manual-fetch:" + str(target), 0))))
            busy_rows = (await session.execute(
                select(DiscoveryChannelModel.publisher_id, DiscoveryChannelModel.fetch_job_id)
                .join(FetchJobModel, FetchJobModel.id == DiscoveryChannelModel.fetch_job_id).where(
                    DiscoveryChannelModel.publisher_id.in_(publisher_ids),
                    DiscoveryChannelModel.active.is_(True),
                    DiscoveryChannelModel.fetch_job_id.is_not(None),
                    FetchJobModel.status.not_in(["completed", "failed", "cancelled"]),
                )
            )).all()
            busy_publishers = {row.publisher_id for row in busy_rows}
            if busy_rows and (publisher_id is not None or len(busy_publishers) == len(publisher_ids)):
                existing = await session.get(FetchJobModel, busy_rows[0].fetch_job_id)
                if existing is None:
                    raise SourceDiscoveryError("Existing fetch no longer available. Please retry.")
                return await _fetch_job_view(session, existing)
            publisher_ids = [key for key in publisher_ids if key not in busy_publishers]
            selected_channels: list[UUID] = []
            priority = case(CHANNEL_PRIORITY, value=DiscoveryChannelModel.channel_type, else_=5)
            for target in publisher_ids:
                available = (await session.execute(select(
                    DiscoveryChannelModel.id, DiscoveryChannelModel.endpoint_url,
                    DiscoveryChannelModel.channel_type,
                ).where(DiscoveryChannelModel.publisher_id == target,
                        DiscoveryChannelModel.active.is_(True))
                 .order_by(priority,
                           DiscoveryChannelModel.config["discovery_source"].astext.is_(None),
                           DiscoveryChannelModel.next_poll_at.asc().nullslast(),
                           DiscoveryChannelModel.id).limit(200))).all()
                eligible = [row.id for row in available if row.channel_type not in
                            {"sitemap", "news_sitemap"} or current_sitemap(row.endpoint_url, now)]
                selected_channels.extend(eligible[:MAX_MANUAL_CHANNELS_PER_PUBLISHER])
            if not selected_channels:
                raise SourceDiscoveryError("No current discovery channels are available for this publisher")

            job = FetchJobModel(
                id=uuid7(),
                publisher_id=publisher_id,
                job_type="publisher" if publisher_id else "all",
                status="scheduled",
                publishers_total=len(publisher_ids),
                publishers_processed=0,
                urls_discovered=0,
                articles_queued=0,
                articles_extracted=0,
                duplicates_skipped=0,
                failed_articles=0,
                message=(
                    "Discovery channels scheduled. Poller and article worker "
                    "will process asynchronously."
                    + (f" {len(busy_publishers)} other publisher(s) already have a fetch in progress."
                       if busy_publishers else "")
                ),
                metadata_={"publisher_ids": [str(item) for item in publisher_ids],
                           "channel_ids": [str(item) for item in selected_channels],
                           "max_new_urls_per_publisher": self._publisher_fetch_limit,
                           "max_new_urls": self._job_fetch_limit},
                created_at=now,
                started_at=now,
                updated_at=now,
            )
            session.add(job)
            await session.execute(
                update(DiscoveryChannelModel)
                .where(
                    DiscoveryChannelModel.id.in_(selected_channels),
                    DiscoveryChannelModel.active.is_(True),
                )
                .values(next_poll_at=now, fetch_job_id=job.id, updated_at=now)
            )
            await _add_outbox(
                session,
                IntegrationEvent(
                    event_type="fetch.job_scheduled",
                    aggregate_type="fetch_job",
                    aggregate_id=job.id,
                    payload={
                        "job_id": str(job.id),
                        "publisher_id": str(publisher_id) if publisher_id else None,
                        "publisher_ids": [str(item) for item in publisher_ids],
                    },
                    producer="source-api",
                    idempotency_key=f"fetch.job_scheduled:{job.id}",
                ),
            )
            return await _fetch_job_view(session, job)

    async def get_fetch_job(self, job_id: UUID) -> FetchJobView | None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(FetchJobModel, job_id)
            if job is None:
                return None
            return await _fetch_job_view(session, job)

    async def delete_publisher(self, publisher_id: UUID) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.get(PublisherModel, publisher_id)
            if row is None:
                return False
            row.active = False
            row.updated_at = now
            await session.execute(
                update(DiscoveryChannelModel)
                .where(DiscoveryChannelModel.publisher_id == publisher_id)
                .values(active=False, updated_at=now, fetch_job_id=None,
                        lease_owner=None, lease_expires_at=None, lease_heartbeat_at=None,
                        lease_version=DiscoveryChannelModel.lease_version + 1)
            )
            await session.flush()
            await pause_disabled_candidates(session, now, publisher_id)
            await session.execute(update(FetchJobModel).where(
                FetchJobModel.publisher_id == publisher_id,
                FetchJobModel.status.not_in(["completed", "failed", "cancelled"]),
            ).values(status="cancelled", completed_at=now, updated_at=now,
                     message="Publisher disabled; remaining fetching paused."))
            return True

    async def get_extraction_profile(
        self,
        publisher_id: UUID,
    ) -> PublisherExtractionProfileView:
        async with self._session_factory() as session:
            publisher = await session.get(PublisherModel, publisher_id)
            if publisher is None:
                raise PublisherNotFoundError(f"publisher not found: {publisher_id}")
            row = await session.scalar(
                select(PublisherExtractionProfileModel).where(
                    PublisherExtractionProfileModel.publisher_id == publisher_id
                )
            )
            if row is None:
                now = datetime.now(UTC)
                return PublisherExtractionProfileView(
                    publisher_id=publisher_id,
                    domain=publisher.canonical_domain,
                    enabled=True,
                    preferred_method="auto",
                    recommended_method=None,
                    low_value_phrases=[],
                    skip_attribute_tokens=[],
                    skip_attribute_phrases=[],
                    paywall_or_partial_phrases=[],
                    browser_render_enabled=False,
                    browser_allowed_domains=[],
                    method_stats={},
                    sample_count=0,
                    full_success_count=0,
                    partial_success_count=0,
                    failure_count=0,
                    last_quality_score=None,
                    last_observed_at=None,
                    updated_at=now,
                )
            return _extraction_profile_view(row)

    async def update_extraction_profile(
        self,
        publisher_id: UUID,
        command: UpdatePublisherExtractionProfileCommand,
    ) -> PublisherExtractionProfileView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            publisher = await session.get(PublisherModel, publisher_id)
            if publisher is None:
                raise PublisherNotFoundError(f"publisher not found: {publisher_id}")
            row = await session.scalar(
                select(PublisherExtractionProfileModel)
                .where(PublisherExtractionProfileModel.publisher_id == publisher_id)
                .with_for_update()
            )
            if row is None:
                row = PublisherExtractionProfileModel(
                    id=uuid7(),
                    publisher_id=publisher_id,
                    domain=publisher.canonical_domain,
                    enabled=command.enabled,
                    preferred_method=command.preferred_method,
                    recommended_method=None,
                    low_value_phrases=command.low_value_phrases,
                    skip_attribute_tokens=command.skip_attribute_tokens,
                    skip_attribute_phrases=command.skip_attribute_phrases,
                    paywall_or_partial_phrases=command.paywall_or_partial_phrases,
                    browser_render_enabled=command.browser_render_enabled,
                    browser_allowed_domains=command.browser_allowed_domains,
                    method_stats={},
                    sample_count=0,
                    full_success_count=0,
                    partial_success_count=0,
                    failure_count=0,
                    last_quality_score=None,
                    last_observed_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                await session.flush()
            else:
                row.enabled = command.enabled
                row.preferred_method = command.preferred_method
                row.low_value_phrases = command.low_value_phrases
                row.skip_attribute_tokens = command.skip_attribute_tokens
                row.skip_attribute_phrases = command.skip_attribute_phrases
                row.paywall_or_partial_phrases = command.paywall_or_partial_phrases
                row.browser_render_enabled = command.browser_render_enabled
                row.browser_allowed_domains = command.browser_allowed_domains
                row.updated_at = now
            return _extraction_profile_view(row)

    async def _validate_endpoints(
        self,
        endpoints: Sequence[DiscoveredEndpoint],
    ) -> tuple[ValidatedEndpoint, ...]:
        """Validate candidate channels and expand one-hop HTML feed directories.

        A number of publishers expose ``/rss`` as an HTML directory whose links
        point to the actual RSS feeds (sometimes on a syndication host such as
        FeedBurner).  Treating the directory itself as malformed XML loses those
        channels.  Expansion is deliberately bounded to one directory hop and a
        fixed candidate budget.
        """
        validated: list[ValidatedEndpoint] = []
        queue: list[tuple[DiscoveredEndpoint, int]] = [(item, 0) for item in endpoints]
        seen: set[str] = set()
        max_candidates = 120

        while queue and len(seen) < max_candidates:
            endpoint, depth = queue.pop(0)
            try:
                normalized = canonicalize_url(
                    endpoint.url,
                    CanonicalizationPolicy(drop_parameters=frozenset()),
                ).normalized
            except ValueError:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)

            try:
                fetched = await self._fetcher.fetch(FetchRequest(url=endpoint.url))
                if fetched.status_code < 200 or fetched.status_code >= 300:
                    continue
                try:
                    validated.append(
                        validate_endpoint_payload(
                            fetched.body,
                            endpoint_url=fetched.final_url,
                            source=endpoint.source,
                            hinted_type=endpoint.hinted_type,
                        )
                    )
                    continue
                except Exception:
                    if depth >= 1 or not _looks_like_html_payload(fetched):
                        raise

                nested = unique_endpoints(
                    discover_alternate_links(
                        fetched.body,
                        homepage_url=fetched.final_url,
                    )
                    + discover_syndication_directory_endpoints(
                        fetched.body,
                        page_url=fetched.final_url,
                    )
                )
                for child in nested:
                    if len(seen) + len(queue) >= max_candidates:
                        break
                    queue.append(
                        (
                            DiscoveredEndpoint(
                                url=child.url,
                                source=f"{endpoint.source}+{child.source}",
                                hinted_type=child.hinted_type,
                                metadata={**endpoint.metadata, **child.metadata},
                            ),
                            depth + 1,
                        )
                    )
            except Exception as exc:
                logger.debug(
                    "discovery_endpoint_validation_failed",
                    endpoint_url=endpoint.url,
                    source=endpoint.source,
                    error_type=type(exc).__name__,
                )
        return tuple(validated)



def _looks_like_html_payload(result: FetchResult) -> bool:
    content_type = str(
        result.headers.get("content-type")
        or result.headers.get("Content-Type")
        or ""
    ).casefold()
    if "html" in content_type:
        return True
    sample = result.body[:512].lstrip().lower()
    return sample.startswith((b"<!doctype html", b"<html", b"<head", b"<body"))

def _extraction_profile_view(
    row: PublisherExtractionProfileModel,
) -> PublisherExtractionProfileView:
    return PublisherExtractionProfileView(
        publisher_id=row.publisher_id,
        domain=row.domain,
        enabled=row.enabled,
        preferred_method=row.preferred_method,
        recommended_method=row.recommended_method,
        low_value_phrases=list(row.low_value_phrases or []),
        skip_attribute_tokens=list(row.skip_attribute_tokens or []),
        skip_attribute_phrases=list(row.skip_attribute_phrases or []),
        paywall_or_partial_phrases=list(row.paywall_or_partial_phrases or []),
        browser_render_enabled=bool(row.browser_render_enabled),
        browser_allowed_domains=list(row.browser_allowed_domains or []),
        method_stats=dict(row.method_stats or {}),
        sample_count=row.sample_count,
        full_success_count=row.full_success_count,
        partial_success_count=row.partial_success_count,
        failure_count=row.failure_count,
        last_quality_score=row.last_quality_score,
        last_observed_at=row.last_observed_at,
        updated_at=row.updated_at,
    )


async def _fetch_target_publishers(
    session: AsyncSession,
    publisher_id: UUID | None,
) -> list[UUID]:
    statement = select(PublisherModel.id).where(PublisherModel.active.is_(True))
    if publisher_id is not None:
        statement = statement.where(PublisherModel.id == publisher_id)
    return list((await session.scalars(statement)).all())


async def _create_channel_if_absent(
    session: AsyncSession,
    *,
    publisher_id: UUID,
    endpoint: ValidatedEndpoint,
    frequency: FetchFrequency,
    now: datetime,
) -> tuple[bool, UUID]:
    normalized = canonicalize_url(
        endpoint.url,
        CanonicalizationPolicy(drop_parameters=frozenset()),
    ).normalized
    existing = await session.scalar(
        select(DiscoveryChannelModel).where(
            DiscoveryChannelModel.publisher_id == publisher_id,
            DiscoveryChannelModel.endpoint_url == normalized,
        )
    )
    if existing is not None:
        return False, existing.id

    policy = _frequency_policy(frequency, now=now)
    channel = DiscoveryChannelModel(
        id=uuid7(),
        publisher_id=publisher_id,
        channel_type=endpoint.channel_type.value,
        endpoint_url=normalized,
        config={
            "discovered_by": DISCOVERY_STRATEGY_VERSION,
            "discovery_source": endpoint.source,
            "validated_item_count": endpoint.item_count,
            **dict(endpoint.metadata),
        },
        strategy_version=DISCOVERY_STRATEGY_VERSION,
        active=True,
        next_poll_at=policy.next_poll_at,
        poll_min_seconds=policy.poll_min_seconds,
        poll_max_seconds=policy.poll_max_seconds,
        current_poll_seconds=policy.current_poll_seconds,
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
    )
    session.add(channel)
    return True, channel.id


async def _publisher_source_view(
    session: AsyncSession,
    publisher: PublisherModel,
) -> PublisherSourceView:
    channel_counts = (
        await session.execute(
            select(DiscoveryChannelModel.channel_type, func.count(DiscoveryChannelModel.id),
                   func.max(DiscoveryChannelModel.last_success_at))
            .where(
                DiscoveryChannelModel.publisher_id == publisher.id,
                DiscoveryChannelModel.active.is_(True),
            )
            .group_by(DiscoveryChannelModel.channel_type)
        )
    ).all()
    count_by_type = {str(kind): int(count) for kind, count, _ in channel_counts}
    last_success = max((success for _, _, success in channel_counts if success), default=None)
    rss_count = (
        count_by_type.get(DiscoveryChannelType.RSS.value, 0)
        + count_by_type.get(DiscoveryChannelType.ATOM.value, 0)
        + count_by_type.get(DiscoveryChannelType.JSON_FEED.value, 0)
    )
    sitemap_count = count_by_type.get(DiscoveryChannelType.SITEMAP.value, 0) + count_by_type.get(
        DiscoveryChannelType.NEWS_SITEMAP.value,
        0,
    )
    articles_discovered = await _publisher_discovered_count(session, publisher.id)
    articles_extracted, last_article_at = (await session.execute(select(
        func.count(ArticleModel.id), func.max(ArticleModel.created_at),
    ).where(ArticleModel.publisher_id == publisher.id))).one()
    failed_articles = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.publisher_id == publisher.id,
            UrlCandidateModel.state == "failed",
        )
    )
    observations = await _publisher_observation_count(session, publisher.id)
    rejected_articles = await session.scalar(select(func.count(UrlCandidateModel.id)).where(
        UrlCandidateModel.publisher_id == publisher.id, UrlCandidateModel.state == "rejected"))
    duplicates_skipped = max(0, observations - articles_discovered)
    return PublisherSourceView(
        id=publisher.id,
        name=publisher.name,
        slug=publisher.slug,
        canonical_domain=publisher.canonical_domain,
        homepage_url=publisher.homepage_url,
        fetch_frequency=FetchFrequency(publisher.fetch_frequency),
        discovery_status=publisher.discovery_status,
        discovery_message=publisher.discovery_message,
        rss_feed_count=rss_count,
        sitemap_count=sitemap_count,
        last_fetched_at=last_success,
        articles_discovered=articles_discovered,
        articles_extracted=int(articles_extracted or 0),
        duplicates_skipped=duplicates_skipped,
        failed_articles=int(failed_articles or 0),
        current_status="active" if publisher.active else "disabled",
        rejected_articles=int(rejected_articles or 0), last_article_at=last_article_at,
        created_at=publisher.created_at,
        updated_at=publisher.updated_at,
    )


async def _fetch_job_view(session: AsyncSession, job: FetchJobModel) -> FetchJobView:
    stats = await _job_stats(session, job.id)
    linked_channels = await session.scalar(
        select(func.count(DiscoveryChannelModel.id)).where(DiscoveryChannelModel.fetch_job_id == job.id)
    )
    pending_candidates = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.id.in_(select(FetchJobObservationModel.candidate_id).where(
                FetchJobObservationModel.fetch_job_id == job.id)),
            UrlCandidateModel.state.in_(["ready", "retry", "leased"]),
        )
    )
    successful_polls = await session.scalar(select(func.count(ChannelPollRunModel.id)).where(
        ChannelPollRunModel.fetch_job_id == job.id,
        ChannelPollRunModel.status.in_(["succeeded", "not_modified"]),
    ))
    derived_status = job.status
    if job.status not in {"cancelled", "failed", "completed"}:
        if not linked_channels and not pending_candidates and stats["publishers_processed"] > 0:
            derived_status = "completed" if successful_polls else "failed"
        elif not linked_channels and pending_candidates:
            derived_status = "processing_articles"
        elif stats["publishers_processed"] > 0 or stats["urls_discovered"] > 0:
            derived_status = "running"
    if derived_status != job.status:
        job.status = derived_status
        job.updated_at = datetime.now(UTC)
        if derived_status in {"completed", "failed", "cancelled"}:
            job.completed_at = job.completed_at or job.updated_at
            job.message = ("Fetch finished. Unchanged reports are counted as duplicates."
                           if derived_status == "completed" else
                           "No discovery channel succeeded. Check source health for the errors.")
    return FetchJobView(
        id=job.id,
        publisher_id=job.publisher_id,
        job_type=job.job_type,
        status=derived_status,
        publishers_total=job.publishers_total,
        publishers_processed=stats["publishers_processed"],
        urls_discovered=stats["urls_discovered"],
        articles_queued=stats["articles_queued"],
        articles_extracted=stats["articles_extracted"],
        duplicates_skipped=stats["duplicates_skipped"],
        failed_articles=stats["failed_articles"],
        message=job.message,
        pending_articles=int(pending_candidates or 0), channels_remaining=int(linked_channels or 0),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


async def _job_stats(
    session: AsyncSession,
    job_id: UUID,
) -> dict[str, int]:
    observed = select(FetchJobObservationModel.candidate_id).where(
        FetchJobObservationModel.fetch_job_id == job_id)
    job_started = select(FetchJobModel.created_at).where(FetchJobModel.id == job_id).scalar_subquery()
    urls_discovered = await session.scalar(
        select(func.count(distinct(FetchJobObservationModel.candidate_id))).where(
            FetchJobObservationModel.fetch_job_id == job_id
        )
    )
    articles_queued = await session.scalar(
        select(func.count(FetchJobObservationModel.id)).where(
            FetchJobObservationModel.fetch_job_id == job_id,
            FetchJobObservationModel.candidate_created.is_(True),
        )
    )
    duplicates_skipped = await session.scalar(
        select(func.count(FetchJobObservationModel.id)).where(
            FetchJobObservationModel.fetch_job_id == job_id,
            FetchJobObservationModel.candidate_created.is_(False),
        )
    )
    articles_extracted = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.id.in_(observed),
            UrlCandidateModel.processing_completed_at >= job_started,
            UrlCandidateModel.article_id.is_not(None),
        )
    )
    failed_articles = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.id.in_(observed),
            UrlCandidateModel.processing_completed_at >= job_started,
            UrlCandidateModel.state == "failed",
        )
    )
    publishers_processed = await session.scalar(
        select(func.count(distinct(DiscoveryChannelModel.publisher_id)))
        .join(ChannelPollRunModel, ChannelPollRunModel.channel_id == DiscoveryChannelModel.id)
        .where(ChannelPollRunModel.fetch_job_id == job_id)
    )
    return {
        "publishers_processed": int(publishers_processed or 0),
        "urls_discovered": int(urls_discovered or 0),
        "articles_queued": int(articles_queued or 0),
        "articles_extracted": int(articles_extracted or 0),
        "duplicates_skipped": int(duplicates_skipped or 0),
        "failed_articles": int(failed_articles or 0),
    }


async def _publisher_discovered_count(session: AsyncSession, publisher_id: UUID) -> int:
    value = await session.scalar(
        select(func.count(UrlCandidateModel.id)).where(
            UrlCandidateModel.publisher_id == publisher_id
        )
    )
    return int(value or 0)


async def _publisher_observation_count(session: AsyncSession, publisher_id: UUID) -> int:
    value = await session.scalar(
        select(func.count(UrlDiscoveryModel.id))
        .join(UrlCandidateModel, UrlCandidateModel.id == UrlDiscoveryModel.url_candidate_id)
        .where(UrlCandidateModel.publisher_id == publisher_id)
    )
    return int(value or 0)


def _frequency_policy(frequency: FetchFrequency, *, now: datetime) -> FrequencyPolicy:
    seconds = {
        FetchFrequency.MANUAL: 3_600,
        FetchFrequency.EVERY_15_MINUTES: 900,
        FetchFrequency.HOURLY: 3_600,
        FetchFrequency.EVERY_6_HOURS: 21_600,
        FetchFrequency.DAILY: 86_400,
    }[frequency]
    return FrequencyPolicy(
        next_poll_at=None if frequency is FetchFrequency.MANUAL else now,
        poll_min_seconds=seconds,
        poll_max_seconds=seconds,
        current_poll_seconds=seconds,
    )


def _slugify(value: str) -> str:
    slug = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value.strip()
    ).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "publisher"


async def _unique_slug(session: AsyncSession, slug: str) -> str:
    existing = set(
        (
            await session.scalars(
                select(PublisherModel.slug).where(PublisherModel.slug.like(f"{slug}%"))
            )
        ).all()
    )
    if slug not in existing:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in existing:
        suffix += 1
    return f"{slug}-{suffix}"


async def _add_outbox(session: AsyncSession, event: IntegrationEvent) -> None:
    await session.execute(
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
