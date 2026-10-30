from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from html import unescape
from typing import Protocol

import httpx

from newsintel.application.historical.dto import (
    ArchiveLookupCommand,
    ArchiveProviderName,
    ArchiveSnapshotView,
    HistoricalArticleView,
    HistoricalProviderName,
    HistoricalResultType,
    HistoricalSearchCommand,
)
from newsintel.application.historical.service import HistoricalProviderError


class HistoricalHttpTransport(Protocol):
    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object: ...

    async def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str: ...


class JsonHttpTransport:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._user_agent = user_agent

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        response = await self._request(url, params=params, headers=headers)
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise HistoricalProviderError(
                "invalid_response",
                "provider returned invalid JSON",
            ) from exc

    async def get_text(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        response = await self._request(url, params=params, headers=headers)
        return response.text

    async def _request(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None,
        headers: Mapping[str, str] | None,
    ) -> httpx.Response:
        request_headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        if headers:
            request_headers.update(headers)
        try:
            response = await self._client.get(
                url,
                params=params,
                headers=request_headers,
            )
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise HistoricalProviderError("timeout", "provider request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise HistoricalProviderError(
                "http_error",
                f"provider returned HTTP {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HistoricalProviderError(
                "network_error",
                "provider request could not be completed",
            ) from exc


class GdeltDocProvider:
    name = HistoricalProviderName.GDELT
    _endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, transport: HistoricalHttpTransport, *, max_results: int = 100) -> None:
        self._transport = transport
        self._max_results = max_results

    @property
    def configured(self) -> bool:
        return True

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]:
        earliest_supported = datetime.now(UTC).date() - timedelta(days=93)
        requested_dates = [value for value in (command.from_date, command.to_date) if value]
        if requested_dates and min(requested_dates) < earliest_supported:
            raise HistoricalProviderError(
                "unsupported_date_range",
                "GDELT DOC search only supports approximately the most recent three months",
            )
        params: dict[str, str | int] = {
            "query": command.query,
            "mode": "ArtList",
            "format": "json",
            "sort": "DateDesc",
            "maxrecords": min(command.limit, self._max_results, 250),
        }
        if command.from_date:
            params["startdatetime"] = _at_start(command.from_date).strftime("%Y%m%d%H%M%S")
        if command.to_date:
            params["enddatetime"] = _at_end(command.to_date).strftime("%Y%m%d%H%M%S")
        payload = _mapping(await self._transport.get_json(self._endpoint, params=params))
        articles = _sequence(payload.get("articles"))
        results: list[HistoricalArticleView] = []
        for raw in articles:
            item = _mapping(raw)
            url = _text(item.get("url"))
            title = _text(item.get("title"))
            if not url or not title:
                continue
            results.append(
                HistoricalArticleView(
                    provider=self.name,
                    title=title,
                    url=url,
                    published_at=_parse_datetime(_text(item.get("seendate"))),
                    source_name=_text(item.get("domain")),
                    language=_text(item.get("language")),
                    image_url=_text(item.get("socialimage")),
                    metadata={
                        "source_country": _text(item.get("sourcecountry")),
                    },
                )
            )
        return results


class GuardianProvider:
    name = HistoricalProviderName.GUARDIAN
    _endpoint = "https://content.guardianapis.com/search"

    def __init__(
        self,
        transport: HistoricalHttpTransport,
        *,
        api_key: str,
        max_results: int = 100,
    ) -> None:
        self._transport = transport
        self._api_key = api_key
        self._max_results = max_results

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]:
        params: dict[str, str | int] = {
            "api-key": self._api_key,
            "q": command.query,
            "order-by": "newest",
            "page-size": min(command.limit, self._max_results, 200),
            "show-fields": "headline,trailText,byline,thumbnail",
        }
        if command.from_date:
            params["from-date"] = command.from_date.isoformat()
        if command.to_date:
            params["to-date"] = command.to_date.isoformat()
        payload = _mapping(await self._transport.get_json(self._endpoint, params=params))
        response = _mapping(payload.get("response"))
        results: list[HistoricalArticleView] = []
        for raw in _sequence(response.get("results")):
            item = _mapping(raw)
            fields = _mapping(item.get("fields"))
            url = _text(item.get("webUrl"))
            title = _text(fields.get("headline")) or _text(item.get("webTitle"))
            if not url or not title:
                continue
            results.append(
                HistoricalArticleView(
                    provider=self.name,
                    title=title,
                    url=url,
                    published_at=_parse_datetime(_text(item.get("webPublicationDate"))),
                    source_name="The Guardian",
                    snippet=_strip_html(_text(fields.get("trailText"))),
                    image_url=_text(fields.get("thumbnail")),
                    metadata={
                        "section": _text(item.get("sectionName")),
                        "byline": _text(fields.get("byline")),
                    },
                )
            )
        return results


class NewYorkTimesProvider:
    name = HistoricalProviderName.NEW_YORK_TIMES
    _endpoint = "https://api.nytimes.com/svc/search/v2/articlesearch.json"

    def __init__(
        self,
        transport: HistoricalHttpTransport,
        *,
        api_key: str,
        max_results: int = 10,
    ) -> None:
        self._transport = transport
        self._api_key = api_key
        self._max_results = max_results

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]:
        params: dict[str, str | int] = {
            "api-key": self._api_key,
            "q": command.query,
            "sort": "newest",
        }
        if command.from_date:
            params["begin_date"] = command.from_date.strftime("%Y%m%d")
        if command.to_date:
            params["end_date"] = command.to_date.strftime("%Y%m%d")
        payload = _mapping(await self._transport.get_json(self._endpoint, params=params))
        response = _mapping(payload.get("response"))
        results: list[HistoricalArticleView] = []
        for raw in _sequence(response.get("docs"))[: min(command.limit, self._max_results)]:
            item = _mapping(raw)
            headline = _mapping(item.get("headline"))
            url = _text(item.get("web_url"))
            title = _text(headline.get("main"))
            if not url or not title:
                continue
            results.append(
                HistoricalArticleView(
                    provider=self.name,
                    title=title,
                    url=url,
                    published_at=_parse_datetime(_text(item.get("pub_date"))),
                    source_name=_text(item.get("source")) or "The New York Times",
                    snippet=_text(item.get("snippet")) or _text(item.get("abstract")),
                    metadata={
                        "section": _text(item.get("section_name")),
                        "document_type": _text(item.get("document_type")),
                    },
                )
            )
        return results


class NewsApiProvider:
    name = HistoricalProviderName.NEWS_API
    _endpoint = "https://newsapi.org/v2/everything"

    def __init__(
        self,
        transport: HistoricalHttpTransport,
        *,
        api_key: str,
        max_results: int = 100,
    ) -> None:
        self._transport = transport
        self._api_key = api_key
        self._max_results = max_results

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]:
        params: dict[str, str | int] = {
            "q": command.query,
            "sortBy": "publishedAt",
            "pageSize": min(command.limit, self._max_results, 100),
        }
        if command.from_date:
            params["from"] = command.from_date.isoformat()
        if command.to_date:
            params["to"] = command.to_date.isoformat()
        if command.language:
            params["language"] = command.language.split("-", maxsplit=1)[0].lower()
        payload = _mapping(
            await self._transport.get_json(
                self._endpoint,
                params=params,
                headers={"X-Api-Key": self._api_key},
            )
        )
        results: list[HistoricalArticleView] = []
        for raw in _sequence(payload.get("articles")):
            item = _mapping(raw)
            source = _mapping(item.get("source"))
            url = _text(item.get("url"))
            title = _text(item.get("title"))
            if not url or not title:
                continue
            results.append(
                HistoricalArticleView(
                    provider=self.name,
                    title=title,
                    url=url,
                    published_at=_parse_datetime(_text(item.get("publishedAt"))),
                    source_name=_text(source.get("name")),
                    snippet=_text(item.get("description")),
                    image_url=_text(item.get("urlToImage")),
                    metadata={"author": _text(item.get("author"))},
                )
            )
        return results


class GoogleFactCheckProvider:
    name = HistoricalProviderName.GOOGLE_FACT_CHECK
    _endpoint = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    def __init__(
        self,
        transport: HistoricalHttpTransport,
        *,
        api_key: str,
        max_results: int = 50,
    ) -> None:
        self._transport = transport
        self._api_key = api_key
        self._max_results = max_results

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]:
        params: dict[str, str | int] = {
            "key": self._api_key,
            "query": command.query,
            "pageSize": min(command.limit, self._max_results),
        }
        if command.language:
            params["languageCode"] = command.language
        payload = _mapping(await self._transport.get_json(self._endpoint, params=params))
        results: list[HistoricalArticleView] = []
        for raw_claim in _sequence(payload.get("claims")):
            claim = _mapping(raw_claim)
            claim_text = _text(claim.get("text"))
            for raw_review in _sequence(claim.get("claimReview")):
                review = _mapping(raw_review)
                publisher = _mapping(review.get("publisher"))
                url = _text(review.get("url"))
                title = _text(review.get("title")) or claim_text
                if not url or not title:
                    continue
                results.append(
                    HistoricalArticleView(
                        provider=self.name,
                        result_type=HistoricalResultType.FACT_CHECK,
                        title=title,
                        url=url,
                        published_at=_parse_datetime(
                            _text(review.get("reviewDate")) or _text(claim.get("claimDate"))
                        ),
                        source_name=_text(publisher.get("name")) or _text(
                            publisher.get("site")
                        ),
                        snippet=claim_text,
                        language=_text(review.get("languageCode")),
                        metadata={
                            "claimant": _text(claim.get("claimant")),
                            "textual_rating": _text(review.get("textualRating")),
                        },
                    )
                )
        return results[: min(command.limit, self._max_results)]


class WaybackArchiveProvider:
    name = ArchiveProviderName.WAYBACK
    _endpoint = "https://archive.org/wayback/available"

    def __init__(self, transport: HistoricalHttpTransport) -> None:
        self._transport = transport

    async def lookup(self, command: ArchiveLookupCommand) -> list[ArchiveSnapshotView]:
        params: dict[str, str | int] = {"url": str(command.url)}
        if command.timestamp:
            params["timestamp"] = command.timestamp.astimezone(UTC).strftime("%Y%m%d%H%M%S")
        payload = _mapping(await self._transport.get_json(self._endpoint, params=params))
        snapshots = _mapping(payload.get("archived_snapshots"))
        closest = _mapping(snapshots.get("closest"))
        archived_url = _text(closest.get("url"))
        if not archived_url or closest.get("available") is not True:
            return []
        return [
            ArchiveSnapshotView(
                provider=self.name,
                original_url=str(command.url),
                archived_url=archived_url,
                captured_at=_parse_datetime(_text(closest.get("timestamp"))),
                status_code=_integer(closest.get("status")),
            )
        ]


class CommonCrawlArchiveProvider:
    name = ArchiveProviderName.COMMON_CRAWL
    _collections_endpoint = "https://index.commoncrawl.org/collinfo.json"

    def __init__(
        self,
        transport: HistoricalHttpTransport,
        *,
        collection_count: int = 3,
    ) -> None:
        self._transport = transport
        self._collection_count = collection_count

    async def lookup(self, command: ArchiveLookupCommand) -> list[ArchiveSnapshotView]:
        payload = await self._transport.get_json(self._collections_endpoint)
        collections = _sequence(payload)[: self._collection_count]
        runs = await asyncio.gather(
            *(self._lookup_collection(_mapping(item), command) for item in collections),
            return_exceptions=True,
        )
        successful = [run for run in runs if isinstance(run, list)]
        if not successful:
            first_error = next((run for run in runs if isinstance(run, Exception)), None)
            if isinstance(first_error, HistoricalProviderError):
                raise first_error
            raise HistoricalProviderError(
                "archive_lookup_failed",
                "all Common Crawl collection lookups failed",
            )
        return [snapshot for run in successful for snapshot in run][: command.limit]

    async def _lookup_collection(
        self,
        collection: dict[str, object],
        command: ArchiveLookupCommand,
    ) -> list[ArchiveSnapshotView]:
        endpoint = _text(collection.get("cdx-api"))
        collection_id = _text(collection.get("id"))
        if not endpoint:
            return []
        text = await self._transport.get_text(
            endpoint,
            params={
                "url": str(command.url),
                "output": "json",
                "filter": "status:200",
                "collapse": "digest",
                "limit": min(command.limit, 50),
            },
        )
        results: list[ArchiveSnapshotView] = []
        for line in text.splitlines():
            try:
                item = _mapping(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
            original = _text(item.get("url")) or str(command.url)
            filename = _text(item.get("filename"))
            offset = _text(item.get("offset"))
            length = _text(item.get("length"))
            timestamp = _text(item.get("timestamp"))
            if not filename or not offset or not length:
                continue
            archived_url = (
                "https://data.commoncrawl.org/"
                f"{filename}#offset={offset}&length={length}"
            )
            results.append(
                ArchiveSnapshotView(
                    provider=self.name,
                    original_url=original,
                    archived_url=archived_url,
                    captured_at=_parse_datetime(timestamp),
                    status_code=_integer(item.get("status")),
                    mime_type=_text(item.get("mime")) or _text(item.get("mime-detected")),
                    digest=_text(item.get("digest")),
                    metadata={"collection": collection_id},
                )
            )
        return results


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return list(value)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(unescape(value).split())
    return normalized or None


def _integer(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return _text(re.sub(r"<[^>]+>", " ", value))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    formats = (
        "%Y%m%dT%H%M%SZ",
        "%Y%m%d%H%M%S",
        "%Y-%m-%dT%H:%M:%SZ",
    )
    for format_string in formats:
        try:
            return datetime.strptime(normalized, format_string).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _at_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _at_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)
