import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from newsintel.workers import recompute, workspace_monitor


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("worker", "service_class", "lease_method"),
    [(recompute, "DerivedArtifactDependencyService", "lease_jobs"),
     (workspace_monitor, "WorkspaceMonitorService", "lease_due")],
)
async def test_worker_retries_database_outage_and_disposes_on_shutdown(
    monkeypatch, worker, service_class, lease_method
):
    database = SimpleNamespace(session_factory=None, dispose=AsyncMock())
    lease = AsyncMock(side_effect=[OSError("database offline"), ()])
    service = SimpleNamespace(**{lease_method: lease})
    monkeypatch.setattr(worker, "Database", lambda settings: database)
    monkeypatch.setattr(worker, service_class, lambda factory: service)
    waits = []

    async def sleep(delay):
        waits.append(delay)
        if len(waits) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker()
    assert lease.await_count == 2
    assert waits[0] > 0
    database.dispose.assert_awaited_once()
