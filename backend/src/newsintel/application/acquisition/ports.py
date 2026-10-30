from contextlib import AbstractAsyncContextManager
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from newsintel.contracts.events import IntegrationEvent
from newsintel.domain.acquisition.entities import (
    DiscoveryChannel,
    Publisher,
    UrlCandidate,
    UrlDiscovery,
)


class DiscoveryBudgetReached(RuntimeError):
    """A manual job reached its configured new-article limit."""


class PublisherRepository(Protocol):
    async def get(self, publisher_id: UUID) -> Publisher | None: ...

    async def get_by_slug(self, slug: str) -> Publisher | None: ...

    async def add(self, publisher: Publisher) -> None: ...


class ChannelRepository(Protocol):
    async def get(self, channel_id: UUID) -> DiscoveryChannel | None: ...

    async def get_by_endpoint(
        self,
        publisher_id: UUID,
        endpoint_url: str,
    ) -> DiscoveryChannel | None: ...

    async def add(self, channel: DiscoveryChannel) -> bool: ...


class FrontierRepository(Protocol):
    async def get_by_fingerprint(self, fingerprint: bytes) -> UrlCandidate | None: ...

    async def add_candidate(self, candidate: UrlCandidate) -> bool: ...

    async def update_candidate_job_metadata(
        self,
        *,
        candidate_id: UUID,
        published_at: datetime | None,
        discovered_at: datetime,
        url_type: str | None = None,
        fetch_job_id: UUID | None = None,
    ) -> UrlCandidate | None: ...

    async def add_discovery_if_absent(self, discovery: UrlDiscovery) -> bool: ...

    async def add_fetch_job_observation(
        self, *, fetch_job_id: UUID, candidate_id: UUID, channel_id: UUID, candidate_created: bool, observed_at: datetime
    ) -> None: ...


class OutboxRepository(Protocol):
    async def add(self, event: IntegrationEvent) -> None: ...


class AcquisitionUnitOfWork(Protocol):
    publishers: PublisherRepository
    channels: ChannelRepository
    frontier: FrontierRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> "AcquisitionUnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[AcquisitionUnitOfWork]: ...
