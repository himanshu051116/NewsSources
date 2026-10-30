import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.adapters.collectors.feeds import (
    parse_feed,
    parse_feed_datetime,
    parse_json_feed,
)
from newsintel.adapters.collectors.sitemaps import (
    SitemapDocumentType,
    parse_sitemap,
)
from newsintel.adapters.collectors.source_discovery import (
    discover_html_article_links,
    infer_sitemap_channel_type,
)
from newsintel.adapters.http.crawl_policy import RobotsDeniedError
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.article_filter import (
    DEFAULT_MAX_NEW_URLS_PER_CHANNEL_POLL,
    DEFAULT_RECENT_WINDOW_HOURS,
    should_admit_article_url,
)
from newsintel.domain.acquisition.entities import DiscoveryChannel
from newsintel.domain.acquisition.models import DiscoveryChannelType
from newsintel.domain.acquisition.scheduling import (
    MAX_CHILD_SITEMAPS_PER_POLL,
    current_sitemap,
)

from .dto import CreateChannelCommand, ObserveDiscoveryCommand
from .ports import DiscoveryBudgetReached
from .service import ResourceConflictError, payload_sha256

logger = structlog.get_logger(__name__)


def _source_text(value: str | None, limit: int) -> str | None:
    """Bound untrusted publisher metadata before constructing admission commands."""
    return value[:limit] if value else None


class PollRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PollRun:
    id: UUID
    channel_id: UUID
    worker_id: str
    trace_id: UUID
    started_at: datetime
    lease_version: int = 0
    fetch_job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PollCompletion:
    run_id: UUID
    channel_id: UUID
    trace_id: UUID
    status: PollRunStatus
    completed_at: datetime
    next_poll_at: datetime
    current_poll_seconds: int
    http_status: int | None = None
    not_modified: bool = False
    discovered_count: int = 0
    admitted_count: int = 0
    observation_count: int = 0
    response_bytes: int = 0
    etag: str | None = None
    last_modified: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    detected_channel_type: DiscoveryChannelType | None = None
    worker_id: str | None = None
    lease_version: int = 0
    config_updates: dict[str, object] | None = None
    fetch_job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PollResult:
    channel_id: UUID
    run_id: UUID
    status: PollRunStatus
    discovered_count: int
    admitted_count: int
    observation_count: int
    next_poll_at: datetime


class PollingRepository(Protocol):
    async def lease_due_channels(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> Sequence[DiscoveryChannel]: ...

    async def schedule_now(self, channel_id: UUID) -> bool: ...

    async def start_run(
        self,
        *,
        channel_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
        lease_version: int = 0,
    ) -> PollRun: ...

    async def heartbeat(
        self, *, channel_id: UUID, worker_id: str, lease_version: int, lease_seconds: int
    ) -> bool: ...

    async def complete(self, completion: PollCompletion) -> None: ...


class Fetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...


class DiscoveryAdmission(Protocol):
    async def observe_discovery(
        self,
        command: ObserveDiscoveryCommand,
        *,
        correlation_id: UUID | None = None,
        traceparent: str | None = None,
    ) -> object: ...

    async def create_channel(self, command: CreateChannelCommand) -> object: ...


class UnsupportedChannelTypeError(ValueError):
    pass


HTML_DISCOVERY_CHANNEL_TYPES = {
    DiscoveryChannelType.HOMEPAGE,
    DiscoveryChannelType.CATEGORY,
    DiscoveryChannelType.TAG,
    DiscoveryChannelType.AUTHOR,
    DiscoveryChannelType.ARCHIVE,
    DiscoveryChannelType.INTERNAL_LINK,
    DiscoveryChannelType.SEARCH,
}


def next_interval_seconds(
    channel: DiscoveryChannel,
    *,
    status: PollRunStatus,
    observation_count: int = 0,
) -> int:
    if status is PollRunStatus.FAILED:
        proposed = channel.current_poll_seconds * 2
    elif observation_count > 0:
        proposed = channel.poll_min_seconds
    elif status is PollRunStatus.NOT_MODIFIED:
        proposed = round(channel.current_poll_seconds * 1.5)
    else:
        proposed = round(channel.current_poll_seconds * 1.25)
    return max(channel.poll_min_seconds, min(channel.poll_max_seconds, proposed))


class ChannelPollService:
    def __init__(
        self,
        *,
        polling_repository: PollingRepository,
        admission: DiscoveryAdmission,
        fetcher: Fetcher,
        recent_article_window_hours: int = DEFAULT_RECENT_WINDOW_HOURS,
        max_new_urls_per_channel_poll: int = DEFAULT_MAX_NEW_URLS_PER_CHANNEL_POLL,
    ) -> None:
        self._polling_repository = polling_repository
        self._admission = admission
        self._fetcher = fetcher
        self._recent_article_window_hours = recent_article_window_hours
        self._max_new_urls_per_channel_poll = max_new_urls_per_channel_poll

    async def poll(self, channel: DiscoveryChannel, worker_id: str) -> PollResult:
        started_at = datetime.now(UTC)
        trace_id = uuid7()
        run = await self._polling_repository.start_run(
            channel_id=channel.id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
            lease_version=channel.lease_version,
        )
        channel.fetch_job_id = run.fetch_job_id
        try:
            fetched = await self._fetcher.fetch(
                FetchRequest(
                    url=channel.endpoint_url,
                    etag=None if channel.config.get("sitemap_index_pending") else channel.etag,
                    last_modified=(None if channel.config.get("sitemap_index_pending")
                                   else channel.last_modified),
                )
            )
            discovered = admitted = observations = 0
            detected_channel_type: DiscoveryChannelType | None = None
            if not fetched.not_modified:
                if fetched.status_code < 200 or fetched.status_code >= 300:
                    raise RuntimeError(f"channel returned HTTP {fetched.status_code}")

                (
                    discovered,
                    admitted,
                    observations,
                    detected_channel_type,
                ) = await self._process_payload(
                    channel,
                    fetched,
                    trace_id,
                )
        except Exception as exc:
            await self._finish(
                channel,
                run,
                status=PollRunStatus.FAILED,
                error_type=type(exc).__name__,
                error_message=str(exc)[:2_000],
            )
            raise
        if fetched.not_modified:
            return await self._finish(
                channel,
                run,
                status=PollRunStatus.NOT_MODIFIED,
                http_status=fetched.status_code,
                not_modified=True,
                response_bytes=len(fetched.body),
                etag=fetched.headers.get("etag") or channel.etag,
                last_modified=(
                    fetched.headers.get("last-modified") or channel.last_modified
                ),
            )
        return await self._finish(
            channel,
            run,
            status=PollRunStatus.SUCCEEDED,
            http_status=fetched.status_code,
            discovered_count=discovered,
            admitted_count=admitted,
            observation_count=observations,
            response_bytes=len(fetched.body),
            etag=fetched.headers.get("etag"),
            last_modified=fetched.headers.get("last-modified"),
            detected_channel_type=detected_channel_type,
        )

    async def _observe_discovery(self, command: ObserveDiscoveryCommand,
                                 *, correlation_id: UUID) -> object | None:
        try:
            return await self._admission.observe_discovery(command, correlation_id=correlation_id)
        except DiscoveryBudgetReached:
            return None

    async def _process_payload(
        self,
        channel: DiscoveryChannel,
        fetched: FetchResult,
        trace_id: UUID,
    ) -> tuple[int, int, int, DiscoveryChannelType | None]:
        body_hash = payload_sha256(fetched.body)
        discovered = 0
        admitted = 0
        observations = 0

        if channel.channel_type in {
            DiscoveryChannelType.RSS,
            DiscoveryChannelType.ATOM,
            DiscoveryChannelType.JSON_FEED,
        }:
            items = (
                parse_json_feed(fetched.body, channel.endpoint_url)
                if channel.channel_type is DiscoveryChannelType.JSON_FEED
                else parse_feed(fetched.body, channel.endpoint_url)
            )
            discovered = len(items)
            seen_urls: set[str] = set()
            for position, item in enumerate(items):
                if admitted >= self._max_new_urls_per_channel_poll:
                    break
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                published_at = parse_feed_datetime(item.published_at_raw)
                decision = should_admit_article_url(
                    item.url,
                    published_at=published_at,
                    observed_at=fetched.retrieved_at,
                    recent_window_hours=self._recent_article_window_hours,
                )
                if not decision.accepted:
                    continue
                result = await self._observe_discovery(
                    ObserveDiscoveryCommand(
                        channel_id=channel.id,
                        url=item.url,
                        external_id=_source_text(item.external_id, 500),
                        title=_source_text(item.title, 1_000),
                        published_at=decision.published_at,
                        published_at_raw=_source_text(item.published_at_raw, 200),
                        discovered_at=fetched.retrieved_at,
                        channel_position=position,
                        payload_sha256=body_hash,
                        fetch_job_id=channel.fetch_job_id,
                    ),
                    correlation_id=trace_id,
                )
                if result is None:
                    break
                admitted += int(bool(getattr(result, "candidate_created", False)))
                observations += int(
                    bool(getattr(result, "channel_observation_created", False))
                )
            detected = items[0].channel_type if items else channel.channel_type
            return discovered, admitted, observations, detected

        if channel.channel_type in {
            DiscoveryChannelType.SITEMAP,
            DiscoveryChannelType.NEWS_SITEMAP,
        }:
            document = parse_sitemap(fetched.body)
            discovered = len(document.entries)
            if document.document_type is SitemapDocumentType.INDEX:
                recent_entries = []
                for entry in document.entries:
                    modified = parse_feed_datetime(entry.last_modified_raw)
                    if current_sitemap(entry.location, fetched.retrieved_at,
                                       self._recent_article_window_hours) and (
                        modified is None or modified >= fetched.retrieved_at - timedelta(
                            hours=self._recent_article_window_hours)
                    ):
                        recent_entries.append(entry)
                recent_entries.sort(key=lambda entry: (
                    parse_feed_datetime(entry.last_modified_raw) or fetched.retrieved_at,
                    entry.location,
                ), reverse=True)
                cursor = channel.config.get("sitemap_index_cursor", 0)
                start = cursor if isinstance(cursor, int) and 0 <= cursor < len(recent_entries) else 0
                chunk = recent_entries[start:start + MAX_CHILD_SITEMAPS_PER_POLL]
                following = start + len(chunk)
                channel.config = dict(channel.config,
                    sitemap_index_cursor=following if following < len(recent_entries) else 0,
                    sitemap_index_pending=following < len(recent_entries))
                for entry in chunk:
                    try:
                        await self._admission.create_channel(
                            CreateChannelCommand(
                                publisher_id=channel.publisher_id,
                                channel_type=infer_sitemap_channel_type(
                                    entry.location,
                                    parent_type=channel.channel_type,
                                ),
                                endpoint_url=entry.location,
                                strategy_version=channel.strategy_version,
                                config={"discovery_source": "sitemap_index",
                                        "parent_channel_id": str(channel.id)},
                                poll_min_seconds=channel.poll_min_seconds,
                                poll_max_seconds=channel.poll_max_seconds,
                                current_poll_seconds=channel.current_poll_seconds,
                            )
                        )
                        admitted += 1
                    except ResourceConflictError:
                        continue
                detected = (
                    DiscoveryChannelType.NEWS_SITEMAP
                    if channel.channel_type is DiscoveryChannelType.NEWS_SITEMAP
                    or document.contains_news
                    else DiscoveryChannelType.SITEMAP
                )
                return discovered, admitted, 0, detected

            for position, entry in enumerate(document.entries):
                if admitted >= self._max_new_urls_per_channel_poll:
                    break
                # Sitemap lastmod describes a change, not original publication.
                published_at_raw = entry.publication_date_raw
                published_at = parse_feed_datetime(published_at_raw)
                decision = should_admit_article_url(
                    entry.location,
                    published_at=published_at,
                    observed_at=fetched.retrieved_at,
                    recent_window_hours=self._recent_article_window_hours,
                )
                if not decision.accepted:
                    continue
                result = await self._observe_discovery(
                    ObserveDiscoveryCommand(
                        channel_id=channel.id,
                        url=entry.location,
                        title=_source_text(entry.news_title, 1_000),
                        published_at=decision.published_at,
                        published_at_raw=_source_text(published_at_raw, 200),
                        discovered_at=fetched.retrieved_at,
                        channel_position=position,
                        payload_sha256=body_hash,
                        fetch_job_id=channel.fetch_job_id,
                    ),
                    correlation_id=trace_id,
                )
                if result is None:
                    break
                admitted += int(bool(getattr(result, "candidate_created", False)))
                observations += int(
                    bool(getattr(result, "channel_observation_created", False))
                )
            detected = (
                DiscoveryChannelType.NEWS_SITEMAP
                if channel.channel_type is DiscoveryChannelType.NEWS_SITEMAP
                or document.contains_news
                else DiscoveryChannelType.SITEMAP
            )
            return discovered, admitted, observations, detected

        if channel.channel_type in HTML_DISCOVERY_CHANNEL_TYPES:
            links = discover_html_article_links(fetched.body, page_url=fetched.final_url)
            discovered = len(links)
            for position, link in enumerate(links):
                if admitted >= self._max_new_urls_per_channel_poll:
                    break
                published_at = parse_feed_datetime(link.published_at_raw)
                decision = should_admit_article_url(
                    link.url,
                    published_at=published_at,
                    observed_at=fetched.retrieved_at,
                    recent_window_hours=self._recent_article_window_hours,
                    require_publication_date=False,
                    trusted_article_evidence=link.structured_data,
                )
                if not decision.accepted:
                    continue
                result = await self._observe_discovery(
                    ObserveDiscoveryCommand(
                        channel_id=channel.id,
                        url=link.url,
                        title=_source_text(link.title, 1_000),
                        published_at=decision.published_at,
                        published_at_raw=_source_text((
                            link.published_at_raw
                            or (
                                decision.published_at.isoformat()
                                if decision.published_at is not None
                                else None
                            )
                        ), 200),
                        discovered_at=fetched.retrieved_at,
                        channel_position=position,
                        payload_sha256=body_hash,
                        fetch_job_id=channel.fetch_job_id,
                    ),
                    correlation_id=trace_id,
                )
                if result is None:
                    break
                admitted += int(bool(getattr(result, "candidate_created", False)))
                observations += int(
                    bool(getattr(result, "channel_observation_created", False))
                )
            return discovered, admitted, observations, channel.channel_type

        raise UnsupportedChannelTypeError(
            f"polling is not implemented for {channel.channel_type.value}"
        )

    async def _finish(
        self,
        channel: DiscoveryChannel,
        run: PollRun,
        *,
        status: PollRunStatus,
        http_status: int | None = None,
        not_modified: bool = False,
        discovered_count: int = 0,
        admitted_count: int = 0,
        observation_count: int = 0,
        response_bytes: int = 0,
        etag: str | None = None,
        last_modified: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        detected_channel_type: DiscoveryChannelType | None = None,
    ) -> PollResult:
        completed_at = datetime.now(UTC)
        interval = next_interval_seconds(
            channel,
            status=status,
            observation_count=observation_count,
        )
        completion = PollCompletion(
            run_id=run.id,
            channel_id=channel.id,
            trace_id=run.trace_id,
            status=status,
            completed_at=completed_at,
            next_poll_at=completed_at + timedelta(seconds=interval),
            current_poll_seconds=interval,
            http_status=http_status,
            not_modified=not_modified,
            discovered_count=discovered_count,
            admitted_count=admitted_count,
            observation_count=observation_count,
            response_bytes=response_bytes,
            etag=etag,
            last_modified=last_modified,
            error_type=error_type,
            error_message=error_message,
            detected_channel_type=detected_channel_type,
            worker_id=run.worker_id,
            lease_version=run.lease_version,
            config_updates={key: channel.config[key] for key in
                            ("sitemap_index_cursor", "sitemap_index_pending")
                            if key in channel.config} or None,
            fetch_job_id=run.fetch_job_id,
        )
        await self._polling_repository.complete(completion)
        return PollResult(
            channel_id=channel.id,
            run_id=run.id,
            status=status,
            discovered_count=discovered_count,
            admitted_count=admitted_count,
            observation_count=observation_count,
            next_poll_at=completion.next_poll_at,
        )


class PollWorker:
    def __init__(
        self,
        *,
        repository: PollingRepository,
        service: ChannelPollService,
        worker_id: str,
        batch_size: int = 20,
        lease_seconds: int = 120,
        concurrency: int = 5,
    ) -> None:
        self._repository = repository
        self._service = service
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._concurrency = concurrency

    async def run_once(self) -> int:
        channels = await self._repository.lease_due_channels(
            worker_id=self._worker_id,
            limit=min(self._batch_size, self._concurrency),
            lease_seconds=self._lease_seconds,
        )
        semaphore = asyncio.Semaphore(self._concurrency)

        async def run(channel: DiscoveryChannel) -> None:
            async with semaphore:
                stop = asyncio.Event()

                async def keepalive() -> None:
                    interval = max(5.0, self._lease_seconds / 3)
                    while not stop.is_set():
                        try:
                            await asyncio.wait_for(stop.wait(), timeout=interval)
                            return
                        except TimeoutError:
                            ok = await self._repository.heartbeat(
                                channel_id=channel.id,
                                worker_id=self._worker_id,
                                lease_version=channel.lease_version,
                                lease_seconds=self._lease_seconds,
                            )
                            if not ok:
                                return

                heartbeat_task = asyncio.create_task(keepalive())
                try:
                    await self._service.poll(channel, self._worker_id)
                except RobotsDeniedError as exc:
                    logger.warning("source_poll_blocked", channel_id=str(channel.id),
                                   error_type=type(exc).__name__, error_message=str(exc)[:500])
                except (OSError, SQLAlchemyError):
                    raise
                except Exception as exc:
                    logger.error("source_poll_failed", channel_id=str(channel.id),
                                 error_type=type(exc).__name__, error_message=str(exc)[:500])
                    return
                finally:
                    stop.set()
                    await heartbeat_task

        outcomes = await asyncio.gather(
            *(run(channel) for channel in channels), return_exceptions=True
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        return len(channels)
