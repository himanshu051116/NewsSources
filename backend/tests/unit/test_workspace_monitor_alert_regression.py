from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from newsintel.application.dependencies.service import LeasedRecomputeJob, _owns_recompute_lease
from newsintel.application.workspace_monitor_service import WorkspaceMonitorService
from newsintel.infrastructure.db.models import WorkspaceGeneratedAlertModel, WorkspaceMonitorRunModel


@pytest.mark.asyncio
async def test_monitor_alert_key_uses_its_run_id_before_flush():
    owner_id, saved_id, monitor_id = uuid4(), uuid4(), uuid4()
    monitor = SimpleNamespace(id=monitor_id, owner_user_id=owner_id, target_id=saved_id,
                              cadence_minutes=15)
    saved = SimpleNamespace(query="policy", filters={}, name="Policy")
    reader = AsyncMock()
    reader.scalar.return_value = saved
    reader.get.return_value = SimpleNamespace(role="analyst", access_status="approved")
    writer = AsyncMock()
    writer.scalar.return_value = SimpleNamespace(result_keys=["article:old"])
    writer.begin = Mock(return_value=AsyncMock())
    added = []
    writer.add = Mock(side_effect=added.append)
    managers = []
    for session in (reader, writer):
        manager = AsyncMock()
        manager.__aenter__.return_value = session
        managers.append(manager)
    service = WorkspaceMonitorService(Mock(side_effect=managers))
    service._leased_monitor = AsyncMock(return_value=monitor)
    service._search_service = SimpleNamespace(search=AsyncMock(return_value=SimpleNamespace(
        results=[SimpleNamespace(result_type="article", id=uuid4())],
    )))
    await service.execute(SimpleNamespace(target_type="saved_search", lease_version=1))
    run = next(item for item in added if isinstance(item, WorkspaceMonitorRunModel))
    alert = next(item for item in added if isinstance(item, WorkspaceGeneratedAlertModel))
    assert run.id is not None
    assert alert.alert_key == f"scheduled-search:{run.id}"


@pytest.mark.parametrize("defect", ["expired", "owner", "attempt", "state"])
def test_recompute_lease_rejects_stale_writer(defect):
    now = datetime.now(UTC)
    job = LeasedRecomputeJob(id=uuid4(), artifact_kind="historical_context", artifact_id=uuid4(),
                            generation=1, reason="changed", attempt_count=2, lease_owner="one")
    row = SimpleNamespace(state="leased", lease_owner="one", attempt_count=2,
                          lease_expires_at=now + timedelta(seconds=60))
    assert _owns_recompute_lease(row, job, now)
    if defect == "expired":
        row.lease_expires_at = now - timedelta(seconds=1)
    elif defect == "owner":
        row.lease_owner = "two"
    elif defect == "attempt":
        row.attempt_count += 1
    else:
        row.state = "completed"
    assert not _owns_recompute_lease(row, job, now)
