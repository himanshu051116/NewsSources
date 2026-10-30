from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.models import (
    ArticleHistoricalContextModel,
    ArticleHistoricalEnrichmentJobModel,
    DerivedArtifactDependencyModel,
    DerivedArtifactStateModel,
    DerivedRecomputeJobModel,
)

HISTORICAL_CONTEXT_ARTIFACT = "historical_context"


@dataclass(frozen=True, slots=True)
class DependencySource:
    kind: str
    id: UUID


@dataclass(frozen=True, slots=True)
class LeasedRecomputeJob:
    id: UUID
    artifact_kind: str
    artifact_id: UUID
    generation: int
    reason: str
    attempt_count: int
    lease_owner: str | None = None


class DerivedArtifactDependencyService:
    """Generic invalidation/recompute registry for derived intelligence artifacts.

    Source facts never get rewritten here. A changed source marks dependent derived
    artifacts stale and creates an idempotent generation-scoped recompute job.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def replace_dependencies(
        self,
        *,
        artifact_kind: str,
        artifact_id: UUID,
        sources: tuple[DependencySource, ...],
        session: AsyncSession | None = None,
    ) -> None:
        if session is not None:
            await _replace_dependencies(session, artifact_kind, artifact_id, sources)
            return
        async with self._session_factory() as owned, owned.begin():
            await _replace_dependencies(owned, artifact_kind, artifact_id, sources)

    async def mark_fresh(
        self,
        *,
        artifact_kind: str,
        artifact_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        if session is not None:
            await _mark_fresh(session, artifact_kind, artifact_id)
            return
        async with self._session_factory() as owned, owned.begin():
            await _mark_fresh(owned, artifact_kind, artifact_id)

    async def invalidate_source(
        self,
        *,
        source_kind: str,
        source_id: UUID,
        reason: str,
        session: AsyncSession | None = None,
    ) -> int:
        if session is not None:
            return await _invalidate_source(session, source_kind, source_id, reason)
        async with self._session_factory() as owned, owned.begin():
            return await _invalidate_source(owned, source_kind, source_id, reason)

    async def lease_jobs(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> list[LeasedRecomputeJob]:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            rows = list(
                (
                    await session.scalars(
                        select(DerivedRecomputeJobModel)
                        .where(
                            DerivedRecomputeJobModel.next_attempt_at <= now,
                            or_(
                                DerivedRecomputeJobModel.state.in_(("queued", "retry")),
                                and_(
                                    DerivedRecomputeJobModel.state == "leased",
                                    DerivedRecomputeJobModel.lease_expires_at < now,
                                ),
                            ),
                        )
                        .order_by(DerivedRecomputeJobModel.next_attempt_at)
                        .with_for_update(skip_locked=True)
                        .limit(limit)
                    )
                ).all()
            )
            leased: list[LeasedRecomputeJob] = []
            for row in rows:
                row.state = "leased"
                row.lease_owner = worker_id
                row.lease_expires_at = now + timedelta(seconds=lease_seconds)
                row.attempt_count += 1
                row.updated_at = now
                leased.append(
                    LeasedRecomputeJob(
                        id=row.id,
                        artifact_kind=row.artifact_kind,
                        artifact_id=row.artifact_id,
                        generation=row.generation,
                        reason=row.reason,
                        attempt_count=row.attempt_count,
                        lease_owner=worker_id,
                    )
                )
            return leased

    async def fail(self, job: LeasedRecomputeJob, exc: Exception) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.get(DerivedRecomputeJobModel, job.id, with_for_update=True)
            if not _owns_recompute_lease(row, job, now):
                return
            assert row is not None
            terminal = job.attempt_count >= 5
            row.state = "failed" if terminal else "retry"
            row.next_attempt_at = now + timedelta(seconds=min(1800, 30 * (2 ** max(0, job.attempt_count - 1))))
            row.lease_owner = None
            row.lease_expires_at = None
            row.last_error = f"{type(exc).__name__}: {str(exc)[:1800]}"
            row.updated_at = now

    async def dispatch(self, job: LeasedRecomputeJob) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            row = await session.get(DerivedRecomputeJobModel, job.id, with_for_update=True)
            if not _owns_recompute_lease(row, job, now):
                return
            assert row is not None
            if job.artifact_kind == HISTORICAL_CONTEXT_ARTIFACT:
                context = await session.get(ArticleHistoricalContextModel, job.artifact_id)
                if context is None:
                    row.state = "completed"
                    row.last_error = "artifact no longer exists"
                else:
                    enrichment = await session.scalar(
                        select(ArticleHistoricalEnrichmentJobModel)
                        .where(
                            ArticleHistoricalEnrichmentJobModel.article_version_id
                            == context.article_version_id
                        )
                        .with_for_update()
                    )
                    if enrichment is None:
                        row.state = "failed"
                        row.last_error = "historical enrichment job is missing"
                    else:
                        enrichment.state = "queued"
                        enrichment.next_attempt_at = now
                        enrichment.lease_owner = None
                        enrichment.lease_expires_at = None
                        enrichment.completed_at = None
                        enrichment.refresh_count += 1
                        enrichment.last_refresh_reason = f"dependency:{job.reason}"[:120]
                        enrichment.updated_at = now
                        row.state = "completed"
            else:
                row.state = "failed"
                row.last_error = f"no recompute handler registered for {job.artifact_kind}"
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now


def _owns_recompute_lease(
    row: DerivedRecomputeJobModel | None, job: LeasedRecomputeJob, now: datetime
) -> bool:
    return (
        row is not None and row.state == "leased"
        and job.lease_owner is not None and row.lease_owner == job.lease_owner
        and row.attempt_count == job.attempt_count
        and row.lease_expires_at is not None and row.lease_expires_at > now
    )


async def _replace_dependencies(
    session: AsyncSession,
    artifact_kind: str,
    artifact_id: UUID,
    sources: tuple[DependencySource, ...],
) -> None:
    now = datetime.now(UTC)
    await session.execute(
        delete(DerivedArtifactDependencyModel).where(
            DerivedArtifactDependencyModel.artifact_kind == artifact_kind,
            DerivedArtifactDependencyModel.artifact_id == artifact_id,
        )
    )
    seen: set[tuple[str, UUID]] = set()
    for source in sources:
        key = (source.kind, source.id)
        if key in seen:
            continue
        seen.add(key)
        session.add(
            DerivedArtifactDependencyModel(
                id=uuid7(),
                artifact_kind=artifact_kind,
                artifact_id=artifact_id,
                source_kind=source.kind,
                source_id=source.id,
                created_at=now,
            )
        )
    await session.execute(
        insert(DerivedArtifactStateModel)
        .values(
            id=uuid7(),
            artifact_kind=artifact_kind,
            artifact_id=artifact_id,
            stale=False,
            stale_reason=None,
            stale_since=None,
            generation=0,
            last_recomputed_at=now,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_derived_artifact_state")
    )


async def _mark_fresh(session: AsyncSession, artifact_kind: str, artifact_id: UUID) -> None:
    now = datetime.now(UTC)
    row = await session.scalar(
        select(DerivedArtifactStateModel)
        .where(
            DerivedArtifactStateModel.artifact_kind == artifact_kind,
            DerivedArtifactStateModel.artifact_id == artifact_id,
        )
        .with_for_update()
    )
    if row is None:
        session.add(
            DerivedArtifactStateModel(
                id=uuid7(),
                artifact_kind=artifact_kind,
                artifact_id=artifact_id,
                stale=False,
                stale_reason=None,
                stale_since=None,
                generation=0,
                last_recomputed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        return
    row.stale = False
    row.stale_reason = None
    row.stale_since = None
    row.last_recomputed_at = now
    row.updated_at = now


async def _invalidate_source(
    session: AsyncSession,
    source_kind: str,
    source_id: UUID,
    reason: str,
) -> int:
    now = datetime.now(UTC)
    dependencies = list(
        (
            await session.scalars(
                select(DerivedArtifactDependencyModel).where(
                    DerivedArtifactDependencyModel.source_kind == source_kind,
                    DerivedArtifactDependencyModel.source_id == source_id,
                )
            )
        ).all()
    )
    count = 0
    for dependency in dependencies:
        state = await session.scalar(
            select(DerivedArtifactStateModel)
            .where(
                DerivedArtifactStateModel.artifact_kind == dependency.artifact_kind,
                DerivedArtifactStateModel.artifact_id == dependency.artifact_id,
            )
            .with_for_update()
        )
        if state is None:
            state = DerivedArtifactStateModel(
                id=uuid7(),
                artifact_kind=dependency.artifact_kind,
                artifact_id=dependency.artifact_id,
                stale=True,
                stale_reason=reason[:240],
                stale_since=now,
                generation=1,
                last_recomputed_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(state)
        else:
            state.generation += 1
            state.stale = True
            state.stale_reason = reason[:240]
            state.stale_since = now
            state.updated_at = now
        await session.flush()
        await session.execute(
            insert(DerivedRecomputeJobModel)
            .values(
                id=uuid7(),
                artifact_kind=dependency.artifact_kind,
                artifact_id=dependency.artifact_id,
                generation=state.generation,
                state="queued",
                reason=reason[:240],
                source_kind=source_kind,
                source_id=source_id,
                attempt_count=0,
                next_attempt_at=now,
                lease_owner=None,
                lease_expires_at=None,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_derived_recompute_generation")
        )
        count += 1
    return count
