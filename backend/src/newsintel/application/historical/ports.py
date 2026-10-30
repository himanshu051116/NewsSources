from __future__ import annotations

from typing import Protocol

from newsintel.application.historical.dto import (
    ArchiveLookupCommand,
    ArchiveProviderName,
    ArchiveSnapshotView,
    HistoricalArticleView,
    HistoricalProviderName,
    HistoricalSearchCommand,
)


class HistoricalNewsProvider(Protocol):
    name: HistoricalProviderName

    @property
    def configured(self) -> bool: ...

    async def search(self, command: HistoricalSearchCommand) -> list[HistoricalArticleView]: ...


class ArchiveLookupProvider(Protocol):
    name: ArchiveProviderName

    async def lookup(self, command: ArchiveLookupCommand) -> list[ArchiveSnapshotView]: ...
