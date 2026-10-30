from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.acquisition.dto import (
    CreateChannelCommand,
    ObserveDiscoveryCommand,
)
from newsintel.application.acquisition.polling import (
    ChannelPollService,
    PollCompletion,
    PollRun,
    PollRunStatus,
    next_interval_seconds,
)
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.entities import DiscoveryChannel
from newsintel.domain.acquisition.models import DiscoveryChannelType


@dataclass(frozen=True)
class AdmissionResult:
    candidate_created: bool
    channel_observation_created: bool


class FakeAdmission:
    def __init__(self) -> None:
        self.observations: list[ObserveDiscoveryCommand] = []
        self.channels: list[CreateChannelCommand] = []

    async def observe_discovery(
        self,
        command: ObserveDiscoveryCommand,
        *,
        correlation_id: UUID | None = None,
        traceparent: str | None = None,
    ) -> AdmissionResult:
        del correlation_id, traceparent
        self.observations.append(command)
        return AdmissionResult(
            candidate_created=True,
            channel_observation_created=True,
        )

    async def create_channel(self, command: CreateChannelCommand) -> object:
        self.channels.append(command)
        return object()


class FakeFetcher:
    def __init__(self, result: FetchResult | Exception) -> None:
        self.result = result
        self.requests: list[object] = []

    async def fetch(self, request: object) -> FetchResult:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakePollingRepository:
    def __init__(self) -> None:
        self.completions: list[PollCompletion] = []

    async def lease_due_channels(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> tuple[DiscoveryChannel, ...]:
        del worker_id, limit, lease_seconds
        return ()

    async def schedule_now(self, channel_id: UUID) -> bool:
        del channel_id
        return True

    async def start_run(
        self,
        *,
        channel_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
        lease_version: int = 0,
    ) -> PollRun:
        return PollRun(
            id=uuid7(),
            channel_id=channel_id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
            lease_version=lease_version,
        )

    async def complete(self, completion: PollCompletion) -> None:
        self.completions.append(completion)


def channel(channel_type: DiscoveryChannelType) -> DiscoveryChannel:
    return DiscoveryChannel(
        id=uuid7(),
        publisher_id=uuid7(),
        channel_type=channel_type,
        endpoint_url="https://example.com/feed",
        strategy_version="test-v1",
        poll_min_seconds=60,
        poll_max_seconds=3_600,
        current_poll_seconds=300,
    )


def fetch_result(
    *,
    status: int = 200,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> FetchResult:
    return FetchResult(
        requested_url="https://example.com/feed",
        final_url="https://example.com/feed",
        status_code=status,
        headers=headers or {},
        body=body,
        body_sha256="0" * 64,
        retrieved_at=datetime.now(UTC),
        redirect_chain=(),
    )


@pytest.mark.asyncio
async def test_rss_poll_admits_items_and_updates_conditional_state() -> None:
    published_at = datetime.now(UTC).isoformat()
    body = f"""<rss><channel>
      <item><guid>1</guid><title>One</title>
      <link>https://example.com/news/one-important-story-today?utm_source=rss</link>
      <pubDate>{published_at}</pubDate></item>
      <item><guid>2</guid><title>Two</title>
      <link>https://example.com/business/two-market-story-today</link>
      <pubDate>{published_at}</pubDate></item>
    </channel></rss>""".encode()
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(
            fetch_result(
                body=body,
                headers={"etag": '"feed-v2"', "last-modified": "Wed, 25 Jun 2026 10:00:00 GMT"},
            )
        ),
    )

    result = await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")

    assert result.status is PollRunStatus.SUCCEEDED
    assert result.discovered_count == 2
    assert result.admitted_count == 2
    assert result.observation_count == 2
    assert len(admission.observations) == 2
    assert repository.completions[0].etag == '"feed-v2"'
    assert repository.completions[0].current_poll_seconds == 60


@pytest.mark.asyncio
async def test_html_channel_poll_admits_recent_article_links_without_pubdate() -> None:
    today = datetime.now(UTC).date()
    dated_path = today.strftime("%Y/%m/%d")
    body = f"""<html><body>
      <a href="/news/{dated_path}/one-important-story-today">One story</a>
      <a href="/topics/artificial-intelligence">Topic page</a>
      <a href="/technology">Technology section</a>
      <a href="/business/markets-rally-after-policy-update">Markets update</a>
    </body></html>""".encode()
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    result = await service.poll(channel(DiscoveryChannelType.HOMEPAGE), "worker-1")

    assert result.status is PollRunStatus.SUCCEEDED
    assert result.discovered_count == 2
    assert result.admitted_count == 2
    assert len(admission.observations) == 2
    assert str(admission.observations[0].url) == (
        f"https://example.com/news/{dated_path}/one-important-story-today"
    )
    assert admission.observations[0].title == "One story"
    assert admission.observations[0].published_at is not None


@pytest.mark.asyncio
async def test_not_modified_poll_slows_schedule_without_parsing() -> None:
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(status=304)),
    )

    result = await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")

    assert result.status is PollRunStatus.NOT_MODIFIED
    assert not admission.observations
    assert repository.completions[0].current_poll_seconds == 450


@pytest.mark.asyncio
async def test_sitemap_index_onboards_child_sitemaps() -> None:
    body = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/news-1.xml</loc></sitemap>
      <sitemap><loc>https://example.com/news-2.xml</loc></sitemap>
    </sitemapindex>"""
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    result = await service.poll(channel(DiscoveryChannelType.SITEMAP), "worker-1")

    assert result.discovered_count == 2
    assert result.admitted_count == 2
    assert len(admission.channels) == 2
    assert all(
        item.channel_type is DiscoveryChannelType.SITEMAP
        for item in admission.channels
    )


@pytest.mark.asyncio
async def test_sitemap_index_skips_archives_and_bounds_child_creation():
    body = ('<sitemapindex><sitemap><loc>https://example.com/2008-01-01.xml</loc></sitemap>'
            + ''.join(f'<sitemap><loc>https://example.com/current-{i}.xml</loc></sitemap>'
                      for i in range(100)) + '</sitemapindex>').encode()
    admission = FakeAdmission()
    service = ChannelPollService(polling_repository=FakePollingRepository(),
                                admission=admission, fetcher=FakeFetcher(fetch_result(body=body)))
    target = channel(DiscoveryChannelType.SITEMAP)
    target.etag = '"same-index"'
    result = await service.poll(target, "worker-1")
    assert result.admitted_count == 30
    assert target.config["sitemap_index_pending"]
    await service.poll(target, "worker-1")
    assert len({str(item.endpoint_url) for item in admission.channels}) == 60
    assert service._fetcher.requests[-1].etag is None
    assert not any("2008" in str(item.endpoint_url) for item in admission.channels)


@pytest.mark.asyncio
async def test_manual_budget_stops_admission_without_failing_the_channel():
    from newsintel.application.acquisition.ports import DiscoveryBudgetReached

    class LimitedAdmission(FakeAdmission):
        async def observe_discovery(self, command, **kwargs):
            if self.observations:
                raise DiscoveryBudgetReached("Limit reached")
            return await super().observe_discovery(command, **kwargs)

    published = datetime.now(UTC).isoformat()
    body = ('<rss><channel>' + ''.join(
        f'<item><link>https://example.com/news/important-story-{i}-today</link>'
        f'<pubDate>{published}</pubDate></item>' for i in range(3)) + '</channel></rss>').encode()
    admission = LimitedAdmission()
    service = ChannelPollService(polling_repository=FakePollingRepository(),
                                admission=admission, fetcher=FakeFetcher(fetch_result(body=body)))
    result = await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")
    assert result.status == PollRunStatus.SUCCEEDED
    assert result.admitted_count == 1


@pytest.mark.asyncio
async def test_failure_is_persisted_and_backoff_increases() -> None:
    repository = FakePollingRepository()
    service = ChannelPollService(
        polling_repository=repository,
        admission=FakeAdmission(),
        fetcher=FakeFetcher(RuntimeError("network unavailable")),
    )

    with pytest.raises(RuntimeError, match="network unavailable"):
        await service.poll(channel(DiscoveryChannelType.RSS), "worker-1")

    completion = repository.completions[0]
    assert completion.status is PollRunStatus.FAILED
    assert completion.error_type == "RuntimeError"
    assert completion.current_poll_seconds == 600


def test_interval_policy_is_bounded() -> None:
    item = channel(DiscoveryChannelType.RSS)
    item.current_poll_seconds = 3_500

    assert (
        next_interval_seconds(item, status=PollRunStatus.NOT_MODIFIED)
        == item.poll_max_seconds
    )


def test_channel_poll_intervals_must_be_consistent() -> None:
    with pytest.raises(ValidationError, match="poll_min_seconds cannot exceed"):
        CreateChannelCommand(
            publisher_id=uuid7(),
            channel_type=DiscoveryChannelType.RSS,
            endpoint_url="https://example.com/rss",
            poll_min_seconds=600,
            poll_max_seconds=300,
            current_poll_seconds=300,
        )


@pytest.mark.asyncio
async def test_json_feed_poll_admits_items() -> None:
    published_at = datetime.now(UTC).isoformat()
    body = f"""{{
      \"version\": \"https://jsonfeed.org/version/1.1\",
      \"items\": [{{
        \"id\": \"1\",
        \"url\": \"https://example.com/news/one-important-story-today\",
        \"title\": \"One\",
        \"date_published\": \"{published_at}\"
      }}]
    }}""".encode()
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    result = await service.poll(channel(DiscoveryChannelType.JSON_FEED), "worker-1")

    assert result.status is PollRunStatus.SUCCEEDED
    assert result.discovered_count == 1
    assert result.admitted_count == 1
    assert len(admission.observations) == 1


@pytest.mark.asyncio
async def test_news_sitemap_index_propagates_news_hint_to_children() -> None:
    body = b"""<sitemapindex xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">
      <sitemap><loc>https://example.com/section-1.xml</loc></sitemap>
    </sitemapindex>"""
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    await service.poll(channel(DiscoveryChannelType.NEWS_SITEMAP), "worker-1")

    assert admission.channels[0].channel_type is DiscoveryChannelType.NEWS_SITEMAP


@pytest.mark.asyncio
async def test_generic_sitemap_channel_detects_news_sitemap_payload() -> None:
    body = b'''<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
      xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url><loc>https://example.com/news/one-important-story-today</loc><news:news>
        <news:publication_date>2026-08-13T00:00:00Z</news:publication_date>
        <news:title>One</news:title>
      </news:news></url>
    </urlset>'''
    repository = FakePollingRepository()
    service = ChannelPollService(
        polling_repository=repository,
        admission=FakeAdmission(),
        fetcher=FakeFetcher(fetch_result(body=body)),
        recent_article_window_hours=168,
    )

    await service.poll(channel(DiscoveryChannelType.SITEMAP), "worker-1")

    assert repository.completions[0].detected_channel_type is DiscoveryChannelType.NEWS_SITEMAP


@pytest.mark.asyncio
async def test_sitemap_modification_date_does_not_make_old_reporting_current():
    modified = datetime.now(UTC).isoformat()
    body = f'<urlset><url><loc>https://example.com/news/2020/01/01/old-report</loc><lastmod>{modified}</lastmod></url></urlset>'.encode()
    repository, admission = FakePollingRepository(), FakeAdmission()
    service = ChannelPollService(polling_repository=repository, admission=admission,
                                 fetcher=FakeFetcher(fetch_result(body=body)))
    await service.poll(channel(DiscoveryChannelType.SITEMAP), "test")
    assert admission.observations == []


@pytest.mark.asyncio
async def test_html_poll_admits_json_ld_news_article_with_opaque_url() -> None:
    published_at = datetime.now(UTC).isoformat()
    body = f'''<html><head>
      <script type="application/ld+json">
      {{
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "url": "/p/123",
        "headline": "Opaque URL story",
        "datePublished": "{published_at}"
      }}
      </script>
    </head><body></body></html>'''.encode()
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(
        polling_repository=repository,
        admission=admission,
        fetcher=FakeFetcher(fetch_result(body=body)),
    )

    result = await service.poll(channel(DiscoveryChannelType.HOMEPAGE), "worker-1")

    assert result.discovered_count == 1
    assert result.admitted_count == 1
    assert str(admission.observations[0].url) == "https://example.com/p/123"
    assert admission.observations[0].published_at_raw == published_at


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [DiscoveryChannelType.RSS, DiscoveryChannelType.NEWS_SITEMAP,
                                  DiscoveryChannelType.HOMEPAGE])
async def test_oversized_publisher_title_does_not_abort_poll(kind) -> None:
    title = "Long publisher headline " * 100
    published = datetime.now(UTC).isoformat()
    url = "https://example.com/news/one-important-story-today"
    if kind is DiscoveryChannelType.RSS:
        body = f"""<rss><channel><item><link>{url}</link><title>{title}</title>
            <guid>{'x' * 600}</guid><pubDate>{published}</pubDate></item>
            </channel></rss>"""
    elif kind is DiscoveryChannelType.NEWS_SITEMAP:
        body = f"""<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
            <url><loc>{url}</loc><news:news><news:title>{title}</news:title>
            <news:publication_date>{published}</news:publication_date></news:news></url></urlset>"""
    else:
        import json

        body = '<html><script type="application/ld+json">' + json.dumps({
            "@type": "NewsArticle", "url": url, "headline": title, "datePublished": published,
        }) + "</script></html>"
    repository = FakePollingRepository()
    admission = FakeAdmission()
    service = ChannelPollService(polling_repository=repository, admission=admission,
                                 fetcher=FakeFetcher(fetch_result(body=body.encode())))
    result = await service.poll(channel(kind), "test")
    assert result.status is PollRunStatus.SUCCEEDED
    assert result.observation_count == 1
    assert admission.observations[0].title == title[:1_000].strip()
    if kind is DiscoveryChannelType.RSS:
        assert len(admission.observations[0].external_id) == 500


@pytest.mark.asyncio
async def test_robots_denial_finishes_only_its_channel_and_does_not_signal_database_outage():
    from unittest.mock import AsyncMock

    from newsintel.adapters.http.crawl_policy import RobotsDeniedError
    from newsintel.application.acquisition.polling import PollWorker

    repository = FakePollingRepository()
    repository.lease_due_channels = AsyncMock(return_value=(
        channel(DiscoveryChannelType.RSS), channel(DiscoveryChannelType.RSS),
    ))
    fetcher = AsyncMock()
    fetcher.fetch.side_effect = [RobotsDeniedError("Publisher policy disallows URL"),
                                 fetch_result(status=304)]
    service = ChannelPollService(polling_repository=repository, admission=FakeAdmission(),
                                 fetcher=fetcher)
    worker = PollWorker(repository=repository, service=service, worker_id="test", concurrency=2)
    assert await worker.run_once() == 2
    assert {item.status for item in repository.completions} == {
        PollRunStatus.FAILED, PollRunStatus.NOT_MODIFIED,
    }
    assert any(item.error_type == "RobotsDeniedError" for item in repository.completions)
