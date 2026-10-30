from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.search.service import IntelligenceSearchService, SearchFilters
from newsintel.application.workspace_dto import WorkspaceMonitorLease
from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.models import (
    PlatformUserModel,
    SavedSearchModel,
    WorkspaceGeneratedAlertModel,
    WorkspaceMonitorModel,
    WorkspaceMonitorRunModel,
)


class WorkspaceMonitorLeaseLostError(RuntimeError):
    pass


class WorkspaceMonitorService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._search_service = IntelligenceSearchService(session_factory)

    async def lease_due(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> list[WorkspaceMonitorLease]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=lease_seconds)
        async with self._session_factory() as session, session.begin():
            rows = list(
                (
                    await session.scalars(
                        select(WorkspaceMonitorModel)
                        .where(
                            WorkspaceMonitorModel.enabled.is_(True),
                            WorkspaceMonitorModel.next_run_at <= now,
                            or_(
                                WorkspaceMonitorModel.lease_expires_at.is_(None),
                                WorkspaceMonitorModel.lease_expires_at < now,
                            ),
                        )
                        .order_by(WorkspaceMonitorModel.next_run_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            leases: list[WorkspaceMonitorLease] = []
            for row in rows:
                row.lease_owner = worker_id
                row.lease_version += 1
                row.lease_expires_at = expires_at
                row.updated_at = now
                leases.append(
                    WorkspaceMonitorLease(
                        id=row.id,
                        owner_user_id=row.owner_user_id,
                        target_type=row.target_type,
                        target_id=row.target_id,
                        cadence_minutes=row.cadence_minutes,
                        lease_owner=worker_id,
                        lease_version=row.lease_version,
                        lease_expires_at=expires_at,
                    )
                )
            return leases

    async def execute(self, lease: WorkspaceMonitorLease) -> None:
        if lease.target_type != "saved_search":
            await self.fail(lease, ValueError(f"unsupported monitor target: {lease.target_type}"))
            return

        async with self._session_factory() as session:
            monitor = await self._leased_monitor(session, lease)
            saved = await session.scalar(
                select(SavedSearchModel).where(
                    SavedSearchModel.id == monitor.target_id,
                    SavedSearchModel.owner_user_id == monitor.owner_user_id,
                )
            )
            owner = await session.get(PlatformUserModel, monitor.owner_user_id)
            if saved is None or owner is None or owner.access_status != "approved":
                raise WorkspaceMonitorLeaseLostError("saved search owner/target is no longer monitorable")
            include_claims = owner.role in {"analyst", "source_manager", "administrator", "owner"}
            query = saved.query
            filters = dict(saved.filters or {})
            result_type = str(filters.get("result_type") or "all")
            saved_name = saved.name

        search_filters = SearchFilters(
            result_type=result_type,
            language=_optional_text(filters.get("language")),
            publisher=_optional_text(filters.get("publisher")),
            lifecycle_status=_optional_text(filters.get("lifecycle_status")),
            from_date=_optional_datetime(filters.get("from_date")),
            to_date=_optional_datetime(filters.get("to_date")),
        )
        search = await self._search_service.search(
            query=query,
            limit=100,
            include_claims=include_claims,
            include_entities=include_claims,
            filters=search_filters,
        )
        results = search.results
        keys = sorted({f"{item.result_type}:{item.id}" for item in results})
        fingerprint = hashlib.sha256(
            json.dumps(keys, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        now = datetime.now(UTC)

        async with self._session_factory() as session, session.begin():
            monitor = await self._leased_monitor(session, lease, lock=True)
            previous = await session.scalar(
                select(WorkspaceMonitorRunModel)
                .where(
                    WorkspaceMonitorRunModel.monitor_id == monitor.id,
                    WorkspaceMonitorRunModel.status == "completed",
                )
                .order_by(desc(WorkspaceMonitorRunModel.started_at))
                .limit(1)
            )
            previous_keys = set(previous.result_keys) if previous is not None else set()
            new_keys = sorted(set(keys) - previous_keys) if previous is not None else []
            run = WorkspaceMonitorRunModel(
                id=uuid7(),
                monitor_id=monitor.id,
                lease_version=lease.lease_version,
                status="completed",
                started_at=now,
                completed_at=now,
                result_fingerprint=fingerprint,
                result_count=len(keys),
                new_result_count=len(new_keys),
                result_keys=keys,
                new_result_keys=new_keys,
                error=None,
                created_at=now,
            )
            session.add(run)
            if new_keys:
                alert = WorkspaceGeneratedAlertModel(
                    owner_user_id=monitor.owner_user_id,
                    alert_key=f"scheduled-search:{run.id}",
                    alert_type="saved_search_new_results",
                    severity="low",
                    title=f"New monitored search results: {saved_name}",
                    detail=(
                        f"{len(new_keys)} result(s) entered the monitored top-result window "
                        f"for ‘{query}’."
                    ),
                    target_type="saved_search",
                    target_id=monitor.target_id,
                    occurred_at=now,
                    link=_search_link(query, filters),
                    metadata_={
                        "monitor_id": str(monitor.id),
                        "saved_search_id": str(monitor.target_id),
                        "new_result_count": len(new_keys),
                        "new_result_keys": new_keys[:20],
                        "result_type": result_type,
                        "scope_note": "Changes are measured against the previous monitored top-result window.",
                    },
                    created_at=now,
                )
                session.add(alert)
            monitor.last_run_at = now
            monitor.last_success_at = now
            monitor.next_run_at = now + timedelta(minutes=monitor.cadence_minutes)
            monitor.lease_owner = None
            monitor.lease_expires_at = None
            monitor.updated_at = now

    async def fail(self, lease: WorkspaceMonitorLease, exc: Exception) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            monitor = await session.scalar(
                select(WorkspaceMonitorModel)
                .where(
                    WorkspaceMonitorModel.id == lease.id,
                    WorkspaceMonitorModel.lease_owner == lease.lease_owner,
                    WorkspaceMonitorModel.lease_version == lease.lease_version,
                    WorkspaceMonitorModel.lease_expires_at > now,
                )
                .with_for_update()
            )
            if monitor is None:
                return
            session.add(
                WorkspaceMonitorRunModel(
                    monitor_id=monitor.id,
                    lease_version=lease.lease_version,
                    status="failed",
                    started_at=now,
                    completed_at=now,
                    result_fingerprint=None,
                    result_count=0,
                    new_result_count=0,
                    result_keys=[],
                    new_result_keys=[],
                    error=f"{type(exc).__name__}: {exc}"[:4_000],
                    created_at=now,
                )
            )
            monitor.last_run_at = now
            monitor.next_run_at = now + timedelta(minutes=monitor.cadence_minutes)
            monitor.lease_owner = None
            monitor.lease_expires_at = None
            monitor.updated_at = now

    async def _leased_monitor(
        self,
        session: AsyncSession,
        lease: WorkspaceMonitorLease,
        *,
        lock: bool = False,
    ) -> WorkspaceMonitorModel:
        statement = select(WorkspaceMonitorModel).where(
            WorkspaceMonitorModel.id == lease.id,
            WorkspaceMonitorModel.enabled.is_(True),
            WorkspaceMonitorModel.lease_owner == lease.lease_owner,
            WorkspaceMonitorModel.lease_version == lease.lease_version,
            WorkspaceMonitorModel.lease_expires_at > datetime.now(UTC),
        )
        if lock:
            statement = statement.with_for_update()
        row = await session.scalar(statement)
        if row is None:
            raise WorkspaceMonitorLeaseLostError("workspace monitor lease is no longer current")
        return row


def _search_link(query: str, filters: dict[str, object] | str) -> str:
    if isinstance(filters, str):
        filters = {"result_type": filters}
    params: dict[str, str] = {"q": query}
    result_type = _optional_text(filters.get("result_type"))
    if result_type and result_type != "all":
        params["type"] = result_type
    for key in ("language", "publisher", "lifecycle_status", "from_date", "to_date"):
        value = _optional_text(filters.get(key))
        if value:
            params[key] = value
    return f"/search?{urlencode(params)}"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_datetime(value: object) -> datetime | None:
    normalized = _optional_text(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
