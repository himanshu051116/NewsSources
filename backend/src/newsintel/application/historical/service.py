from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from newsintel.application.historical.dto import (
    ArchiveLookupCommand,
    ArchiveLookupResponse,
    ArchiveProviderName,
    ArchiveProviderStatus,
    ArchiveSnapshotView,
    HistoricalArticleView,
    HistoricalProviderName,
    HistoricalProviderStatus,
    HistoricalSearchCommand,
    HistoricalSearchResponse,
    HistoricalTimelineSummary,
)
from newsintel.application.historical.ports import ArchiveLookupProvider, HistoricalNewsProvider
from newsintel.domain.acquisition.canonicalization import canonicalize_url


class HistoricalProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class HistoricalSearchService:
    def __init__(
        self,
        *,
        providers: list[HistoricalNewsProvider],
        archive_providers: list[ArchiveLookupProvider],
        timeout_seconds: float,
    ) -> None:
        self._providers = {provider.name: provider for provider in providers}
        self._archive_providers = {
            provider.name: provider for provider in archive_providers
        }
        self._timeout_seconds = timeout_seconds

    async def search(self, command: HistoricalSearchCommand) -> HistoricalSearchResponse:
        selected = command.providers or list(self._providers)
        runs = await asyncio.gather(
            *(self._run_provider(name, command) for name in selected)
        )
        combined: list[HistoricalArticleView] = []
        statuses: list[HistoricalProviderStatus] = []
        for results, status in runs:
            combined.extend(results)
            statuses.append(status)
        deduplicated, collapsed = _deduplicate_results(combined)
        deduplicated.sort(
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return HistoricalSearchResponse(
            query=command.query,
            from_date=command.from_date,
            to_date=command.to_date,
            results=deduplicated[: command.limit],
            provider_statuses=statuses,
            duplicates_collapsed=collapsed,
            timeline_summary=_timeline_summary(deduplicated),
            generated_at=datetime.now(UTC),
        )

    async def lookup_archives(self, command: ArchiveLookupCommand) -> ArchiveLookupResponse:
        selected = command.providers or list(self._archive_providers)
        runs = await asyncio.gather(
            *(self._run_archive_provider(name, command) for name in selected)
        )
        snapshots: list[ArchiveSnapshotView] = []
        statuses: list[ArchiveProviderStatus] = []
        for results, status in runs:
            snapshots.extend(results)
            statuses.append(status)
        unique: dict[tuple[str, str], ArchiveSnapshotView] = {}
        for snapshot in snapshots:
            unique[(snapshot.provider.value, snapshot.archived_url)] = snapshot
        ordered = sorted(
            unique.values(),
            key=lambda item: item.captured_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return ArchiveLookupResponse(
            url=str(command.url),
            snapshots=ordered[: command.limit],
            provider_statuses=statuses,
            generated_at=datetime.now(UTC),
        )

    async def _run_provider(
        self,
        name: HistoricalProviderName,
        command: HistoricalSearchCommand,
    ) -> tuple[list[HistoricalArticleView], HistoricalProviderStatus]:
        provider = self._providers.get(name)
        if provider is None:
            return [], HistoricalProviderStatus(
                provider=name,
                configured=False,
                success=False,
                error_code="unsupported_provider",
                message="provider is not available in this deployment",
            )
        if not provider.configured:
            return [], HistoricalProviderStatus(
                provider=name,
                configured=False,
                success=False,
                error_code="not_configured",
                message="provider API key is not configured",
            )
        try:
            results = await asyncio.wait_for(
                provider.search(command),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            return [], HistoricalProviderStatus(
                provider=name,
                configured=True,
                success=False,
                error_code="timeout",
                message="provider did not respond before the configured timeout",
            )
        except HistoricalProviderError as exc:
            return [], HistoricalProviderStatus(
                provider=name,
                configured=True,
                success=False,
                error_code=exc.code,
                message=str(exc),
            )
        except Exception as exc:
            return [], HistoricalProviderStatus(
                provider=name,
                configured=True,
                success=False,
                error_code="provider_error",
                message=f"provider request failed: {type(exc).__name__}",
            )
        return results, HistoricalProviderStatus(
            provider=name,
            configured=True,
            success=True,
            result_count=len(results),
        )

    async def _run_archive_provider(
        self,
        name: ArchiveProviderName,
        command: ArchiveLookupCommand,
    ) -> tuple[list[ArchiveSnapshotView], ArchiveProviderStatus]:
        provider = self._archive_providers.get(name)
        if provider is None:
            return [], ArchiveProviderStatus(
                provider=name,
                success=False,
                error_code="unsupported_provider",
                message="archive provider is not available in this deployment",
            )
        try:
            results = await asyncio.wait_for(
                provider.lookup(command),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            return [], ArchiveProviderStatus(
                provider=name,
                success=False,
                error_code="timeout",
                message="archive provider did not respond before the configured timeout",
            )
        except HistoricalProviderError as exc:
            return [], ArchiveProviderStatus(
                provider=name,
                success=False,
                error_code=exc.code,
                message=str(exc),
            )
        except Exception as exc:
            return [], ArchiveProviderStatus(
                provider=name,
                success=False,
                error_code="provider_error",
                message=f"archive lookup failed: {type(exc).__name__}",
            )
        return results, ArchiveProviderStatus(
            provider=name,
            success=True,
            result_count=len(results),
        )


def _deduplicate_results(
    results: list[HistoricalArticleView],
) -> tuple[list[HistoricalArticleView], int]:
    unique: dict[str, HistoricalArticleView] = {}
    counts: dict[str, int] = {}
    providers: dict[str, set[str]] = {}
    source_names: dict[str, set[str]] = {}
    for item in results:
        key = _result_key(item)
        counts[key] = counts.get(key, 0) + 1
        providers.setdefault(key, set()).add(item.provider.value)
        if item.source_name:
            source_names.setdefault(key, set()).add(item.source_name)
        existing = unique.get(key)
        if existing is None or _prefer(item, existing):
            unique[key] = item

    enriched: list[HistoricalArticleView] = []
    for key, item in unique.items():
        metadata = dict(item.metadata)
        metadata.update(
            {
                "provider_mentions": sorted(providers.get(key, {item.provider.value})),
                "provider_mention_count": len(providers.get(key, {item.provider.value})),
                "collapsed_result_count": counts.get(key, 1),
                "source_names_observed": sorted(source_names.get(key, set())),
            }
        )
        enriched.append(item.model_copy(update={"metadata": metadata}))
    return enriched, max(0, len(results) - len(unique))


def _result_key(item: HistoricalArticleView) -> str:
    try:
        return f"url:{canonicalize_url(item.url).normalized}"
    except ValueError:
        normalized_title = " ".join(item.title.lower().split())
        published_day = item.published_at.date().isoformat() if item.published_at else ""
        return f"title:{normalized_title}:{published_day}"


def _prefer(candidate: HistoricalArticleView, existing: HistoricalArticleView) -> bool:
    candidate_score = int(bool(candidate.snippet)) + int(bool(candidate.source_name))
    existing_score = int(bool(existing.snippet)) + int(bool(existing.source_name))
    return candidate_score > existing_score


def _timeline_summary(results: list[HistoricalArticleView]) -> HistoricalTimelineSummary:
    dated = [item.published_at for item in results if item.published_at is not None]
    counts_by_year: dict[str, int] = {}
    for published_at in dated:
        year = str(published_at.year)
        counts_by_year[year] = counts_by_year.get(year, 0) + 1
    source_names = {item.source_name for item in results if item.source_name}
    providers: set[str] = set()
    for item in results:
        mentions = item.metadata.get("provider_mentions")
        if isinstance(mentions, list):
            providers.update(str(value) for value in mentions)
        else:
            providers.add(item.provider.value)
    return HistoricalTimelineSummary(
        result_count=len(results),
        earliest_published_at=min(dated) if dated else None,
        latest_published_at=max(dated) if dated else None,
        result_counts_by_year=dict(sorted(counts_by_year.items())),
        source_count=len(source_names),
        provider_count=len(providers),
    )
