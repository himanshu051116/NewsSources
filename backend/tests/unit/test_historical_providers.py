from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta

import pytest

from newsintel.adapters.historical.providers import (
    CommonCrawlArchiveProvider,
    GdeltDocProvider,
    GoogleFactCheckProvider,
    GuardianProvider,
    NewsApiProvider,
    NewYorkTimesProvider,
    WaybackArchiveProvider,
)
from newsintel.application.historical.dto import (
    ArchiveLookupCommand,
    HistoricalProviderName,
    HistoricalResultType,
    HistoricalSearchCommand,
)
from newsintel.application.historical.service import HistoricalProviderError


class FakeTransport:
    def __init__(
        self,
        *,
        json_by_url: dict[str, object] | None = None,
        text_by_url: dict[str, str] | None = None,
        errors_by_url: dict[str, Exception] | None = None,
    ) -> None:
        self.json_by_url = json_by_url or {}
        self.text_by_url = text_by_url or {}
        self.errors_by_url = errors_by_url or {}
        self.calls: list[tuple[str, Mapping[str, str | int] | None, Mapping[str, str] | None]] = []

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        self.calls.append((url, params, headers))
        error = self.errors_by_url.get(url)
        if error:
            raise error
        return self.json_by_url[url]

    async def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        self.calls.append((url, params, headers))
        error = self.errors_by_url.get(url)
        if error:
            raise error
        return self.text_by_url[url]


@pytest.mark.asyncio
async def test_gdelt_provider_parses_results_and_date_bounds() -> None:
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    transport = FakeTransport(
        json_by_url={
            endpoint: {
                "articles": [
                    {
                        "url": "https://example.com/story",
                        "title": "Global event",
                        "seendate": "20260720T101500Z",
                        "domain": "example.com",
                        "language": "English",
                        "sourcecountry": "India",
                    }
                ]
            }
        }
    )
    provider = GdeltDocProvider(transport, max_results=20)

    today = datetime.now(UTC).date()
    from_date = today - timedelta(days=10)
    results = await provider.search(
        HistoricalSearchCommand(
            query="global event",
            from_date=from_date,
            to_date=today,
            limit=10,
        )
    )

    assert results[0].provider is HistoricalProviderName.GDELT
    assert results[0].published_at == datetime(2026, 7, 20, 10, 15, tzinfo=UTC)
    params = transport.calls[0][1]
    assert params is not None
    assert params["startdatetime"] == f"{from_date:%Y%m%d}000000"
    assert params["enddatetime"] == f"{today:%Y%m%d}235959"
    assert params["maxrecords"] == 10


@pytest.mark.asyncio
async def test_guardian_provider_strips_html_and_limits_page_size() -> None:
    endpoint = "https://content.guardianapis.com/search"
    transport = FakeTransport(
        json_by_url={
            endpoint: {
                "response": {
                    "results": [
                        {
                            "webUrl": "https://theguardian.com/a",
                            "webPublicationDate": "2026-07-20T09:00:00Z",
                            "sectionName": "World",
                            "fields": {
                                "headline": "Headline",
                                "trailText": "<p>Useful <strong>summary</strong></p>",
                                "byline": "Reporter",
                            },
                        }
                    ]
                }
            }
        }
    )
    provider = GuardianProvider(transport, api_key="secret", max_results=500)

    results = await provider.search(HistoricalSearchCommand(query="headline", limit=200))

    assert results[0].snippet == "Useful summary"
    params = transport.calls[0][1]
    assert params is not None
    assert params["page-size"] == 200
    assert params["api-key"] == "secret"


@pytest.mark.asyncio
async def test_new_york_times_provider_parses_article() -> None:
    endpoint = "https://api.nytimes.com/svc/search/v2/articlesearch.json"
    transport = FakeTransport(
        json_by_url={
            endpoint: {
                "response": {
                    "docs": [
                        {
                            "web_url": "https://nytimes.com/a",
                            "pub_date": "2026-07-19T10:00:00+00:00",
                            "headline": {"main": "NYT headline"},
                            "source": "The New York Times",
                            "snippet": "Summary",
                        }
                    ]
                }
            }
        }
    )
    provider = NewYorkTimesProvider(transport, api_key="key", max_results=10)

    results = await provider.search(HistoricalSearchCommand(query="topic", limit=5))

    assert results[0].title == "NYT headline"
    assert results[0].source_name == "The New York Times"


@pytest.mark.asyncio
async def test_news_api_uses_header_key_and_normalizes_language() -> None:
    endpoint = "https://newsapi.org/v2/everything"
    transport = FakeTransport(
        json_by_url={
            endpoint: {
                "articles": [
                    {
                        "url": "https://example.org/a",
                        "title": "Article",
                        "publishedAt": "2026-07-20T07:00:00Z",
                        "source": {"name": "Example"},
                    }
                ]
            }
        }
    )
    provider = NewsApiProvider(transport, api_key="key", max_results=100)

    await provider.search(
        HistoricalSearchCommand(query="article", language="en-IN", limit=5)
    )

    _, params, headers = transport.calls[0]
    assert params is not None and params["language"] == "en"
    assert headers == {"X-Api-Key": "key"}


@pytest.mark.asyncio
async def test_google_fact_check_maps_claim_review() -> None:
    endpoint = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    transport = FakeTransport(
        json_by_url={
            endpoint: {
                "claims": [
                    {
                        "text": "A checkable claim",
                        "claimant": "Person",
                        "claimReview": [
                            {
                                "url": "https://factcheck.example/review",
                                "title": "Review title",
                                "reviewDate": "2026-07-18T00:00:00Z",
                                "textualRating": "False",
                                "publisher": {"name": "Fact Checker"},
                            }
                        ],
                    }
                ]
            }
        }
    )
    provider = GoogleFactCheckProvider(transport, api_key="key")

    results = await provider.search(HistoricalSearchCommand(query="claim"))

    assert results[0].result_type is HistoricalResultType.FACT_CHECK
    assert results[0].metadata["textual_rating"] == "False"
    assert results[0].snippet == "A checkable claim"


@pytest.mark.asyncio
async def test_wayback_provider_parses_closest_snapshot() -> None:
    endpoint = "https://archive.org/wayback/available"
    transport = FakeTransport(
        json_by_url={
            endpoint: {
                "archived_snapshots": {
                    "closest": {
                        "available": True,
                        "url": "https://web.archive.org/web/20200102030405/https://example.com",
                        "timestamp": "20200102030405",
                        "status": "200",
                    }
                }
            }
        }
    )
    provider = WaybackArchiveProvider(transport)

    results = await provider.lookup(
        ArchiveLookupCommand(url="https://example.com", limit=5)
    )

    assert results[0].captured_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert results[0].status_code == 200


@pytest.mark.asyncio
async def test_common_crawl_returns_partial_results_when_one_collection_fails() -> None:
    collections_endpoint = "https://index.commoncrawl.org/collinfo.json"
    first = "https://index.commoncrawl.org/CC-MAIN-2026-30-index"
    second = "https://index.commoncrawl.org/CC-MAIN-2026-26-index"
    transport = FakeTransport(
        json_by_url={
            collections_endpoint: [
                {"id": "CC-MAIN-2026-30", "cdx-api": first},
                {"id": "CC-MAIN-2026-26", "cdx-api": second},
            ]
        },
        text_by_url={
            first: (
                '{"url":"https://example.com/","timestamp":"20260701010101",'
                '"status":"200","mime":"text/html","digest":"ABC",'
                '"filename":"crawl/file.warc.gz","offset":"1","length":"2"}'
            )
        },
        errors_by_url={
            second: HistoricalProviderError("timeout", "collection timed out")
        },
    )
    provider = CommonCrawlArchiveProvider(transport, collection_count=2)

    results = await provider.lookup(
        ArchiveLookupCommand(url="https://example.com", limit=10)
    )

    assert len(results) == 1
    assert results[0].metadata["collection"] == "CC-MAIN-2026-30"
    assert results[0].digest == "ABC"


@pytest.mark.asyncio
async def test_common_crawl_fails_when_all_collections_fail() -> None:
    collections_endpoint = "https://index.commoncrawl.org/collinfo.json"
    first = "https://index.commoncrawl.org/CC-MAIN-2026-30-index"
    transport = FakeTransport(
        json_by_url={
            collections_endpoint: [{"id": "CC-MAIN-2026-30", "cdx-api": first}]
        },
        errors_by_url={
            first: HistoricalProviderError("timeout", "collection timed out")
        },
    )
    provider = CommonCrawlArchiveProvider(transport, collection_count=1)

    with pytest.raises(HistoricalProviderError, match="collection timed out"):
        await provider.lookup(ArchiveLookupCommand(url="https://example.com"))


@pytest.mark.asyncio
async def test_gdelt_provider_rejects_dates_outside_rolling_window() -> None:
    provider = GdeltDocProvider(FakeTransport())

    with pytest.raises(HistoricalProviderError, match="most recent three months"):
        await provider.search(
            HistoricalSearchCommand(
                query="old event",
                from_date=date(2010, 1, 1),
                to_date=date(2010, 1, 2),
            )
        )
