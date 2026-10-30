from __future__ import annotations

from datetime import UTC, datetime

import pytest

from newsintel.application.historical.dto import (
    ArchiveLookupCommand,
    ArchiveProviderName,
    ArchiveSnapshotView,
    HistoricalArticleView,
    HistoricalProviderName,
    HistoricalSearchCommand,
)
from newsintel.application.historical.service import (
    HistoricalProviderError,
    HistoricalSearchService,
)


class _FakeNewsProvider:
    def __init__(
        self,
        name: HistoricalProviderName,
        results: list[HistoricalArticleView],
        *,
        configured: bool = True,
        failure: bool = False,
    ) -> None:
        self.name = name
        self._results = results
        self._configured = configured
        self._failure = failure

    @property
    def configured(self) -> bool:
        return self._configured

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]:
        del command
        if self._failure:
            raise HistoricalProviderError("rate_limited", "provider quota exceeded")
        return self._results


class _FakeArchiveProvider:
    name = ArchiveProviderName.WAYBACK

    async def lookup(self, command: ArchiveLookupCommand) -> list[ArchiveSnapshotView]:
        return [
            ArchiveSnapshotView(
                provider=self.name,
                original_url=str(command.url),
                archived_url="https://web.archive.org/web/20200101000000/https://example.com/story",
                captured_at=datetime(2020, 1, 1, tzinfo=UTC),
                status_code=200,
            )
        ]


@pytest.mark.asyncio
async def test_historical_search_isolates_provider_failure_and_collapses_duplicates() -> None:
    duplicate_url = "https://example.com/story?utm_source=test"
    providers = [
        _FakeNewsProvider(
            HistoricalProviderName.GDELT,
            [
                HistoricalArticleView(
                    provider=HistoricalProviderName.GDELT,
                    title="Example story",
                    url=duplicate_url,
                    published_at=datetime(2026, 7, 20, tzinfo=UTC),
                )
            ],
        ),
        _FakeNewsProvider(
            HistoricalProviderName.GUARDIAN,
            [
                HistoricalArticleView(
                    provider=HistoricalProviderName.GUARDIAN,
                    title="Example story",
                    url="https://example.com/story",
                    published_at=datetime(2026, 7, 20, tzinfo=UTC),
                    snippet="A more complete description.",
                )
            ],
        ),
        _FakeNewsProvider(
            HistoricalProviderName.NEWS_API,
            [],
            failure=True,
        ),
    ]
    service = HistoricalSearchService(
        providers=providers,
        archive_providers=[_FakeArchiveProvider()],
        timeout_seconds=1,
    )

    response = await service.search(HistoricalSearchCommand(query="example"))

    assert len(response.results) == 1
    assert response.results[0].provider is HistoricalProviderName.GUARDIAN
    assert response.duplicates_collapsed == 1
    failed = next(
        item
        for item in response.provider_statuses
        if item.provider is HistoricalProviderName.NEWS_API
    )
    assert not failed.success
    assert failed.error_code == "rate_limited"


@pytest.mark.asyncio
async def test_unconfigured_provider_is_reported_without_calling_it() -> None:
    service = HistoricalSearchService(
        providers=[
            _FakeNewsProvider(
                HistoricalProviderName.GUARDIAN,
                [],
                configured=False,
            )
        ],
        archive_providers=[],
        timeout_seconds=1,
    )

    response = await service.search(
        HistoricalSearchCommand(
            query="history",
            providers=[HistoricalProviderName.GUARDIAN],
        )
    )

    assert response.results == []
    assert response.provider_statuses[0].error_code == "not_configured"


@pytest.mark.asyncio
async def test_archive_lookup_returns_provider_snapshots() -> None:
    service = HistoricalSearchService(
        providers=[],
        archive_providers=[_FakeArchiveProvider()],
        timeout_seconds=1,
    )

    response = await service.lookup_archives(
        ArchiveLookupCommand(url="https://example.com/story")
    )

    assert len(response.snapshots) == 1
    assert response.provider_statuses[0].success


@pytest.mark.asyncio
async def test_historical_search_preserves_provider_provenance_and_builds_timeline_summary() -> None:
    providers = [
        _FakeNewsProvider(
            HistoricalProviderName.GDELT,
            [
                HistoricalArticleView(
                    provider=HistoricalProviderName.GDELT,
                    title="Shared historical report",
                    url="https://example.com/story?utm_source=gdelt",
                    published_at=datetime(2024, 5, 1, tzinfo=UTC),
                    source_name="Example News",
                )
            ],
        ),
        _FakeNewsProvider(
            HistoricalProviderName.GUARDIAN,
            [
                HistoricalArticleView(
                    provider=HistoricalProviderName.GUARDIAN,
                    title="Shared historical report",
                    url="https://example.com/story",
                    published_at=datetime(2024, 5, 1, tzinfo=UTC),
                    source_name="Example News",
                    snippet="Richer provider result.",
                )
            ],
        ),
    ]
    service = HistoricalSearchService(
        providers=providers,
        archive_providers=[],
        timeout_seconds=1,
    )

    response = await service.search(HistoricalSearchCommand(query="shared history"))

    assert len(response.results) == 1
    assert response.results[0].metadata["provider_mentions"] == ["gdelt", "guardian"]
    assert response.results[0].metadata["collapsed_result_count"] == 2
    assert response.timeline_summary is not None
    assert response.timeline_summary.result_count == 1
    assert response.timeline_summary.result_counts_by_year == {"2024": 1}
    assert response.timeline_summary.provider_count == 2
