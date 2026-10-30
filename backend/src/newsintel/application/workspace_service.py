from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.workspace_dto import (
    AnalystNoteCreateCommand,
    AnalystNoteView,
    InvestigationActivityView,
    InvestigationCreateCommand,
    InvestigationDetailView,
    InvestigationManifestView,
    InvestigationMemberCreateCommand,
    InvestigationMemberUpdateCommand,
    InvestigationMemberView,
    InvestigationSummaryView,
    InvestigationUpdateCommand,
    SavedSearchCreateCommand,
    SavedSearchMonitorCommand,
    SavedSearchView,
    WatchlistCreateCommand,
    WatchlistDetailView,
    WatchlistSummaryView,
    WorkspaceAlertView,
    WorkspaceItemCreateCommand,
    WorkspaceItemView,
    WorkspaceMonitorRunView,
    WorkspaceMonitorView,
    WorkspaceOverviewView,
)
from newsintel.infrastructure.db.models import (
    AnalystNoteModel,
    ArticleClaimModel,
    ArticleCorrectionEventModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimEvidenceLinkModel,
    ClaimReviewFlagModel,
    ClaimVerificationModel,
    EventModel,
    InvestigationActivityModel,
    InvestigationItemModel,
    InvestigationMemberModel,
    InvestigationModel,
    PlatformUserModel,
    SavedSearchModel,
    WatchlistItemModel,
    WatchlistModel,
    WorkspaceAlertAcknowledgementModel,
    WorkspaceGeneratedAlertModel,
    WorkspaceMonitorModel,
    WorkspaceMonitorRunModel,
)


class WorkspaceNotFoundError(LookupError):
    pass


class WorkspaceConflictError(ValueError):
    pass


class WorkspaceValidationError(ValueError):
    pass


class WorkspacePermissionError(PermissionError):
    pass


_ACCESS_LEVEL = {"reader": 1, "editor": 2, "owner": 3}


class AnalystWorkspaceService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def overview(self, user_id: UUID) -> WorkspaceOverviewView:
        async with self._session_factory() as session:
            investigations = await self._list_investigations(session, user_id)
            watchlists = await self._list_watchlists(session, user_id)
            saved = await self._list_saved_searches(session, user_id)
            alerts = await self._alerts(session, user_id, include_acknowledged=False)
            return WorkspaceOverviewView(
                investigations=investigations,
                watchlists=watchlists,
                saved_searches=saved,
                alerts=alerts[:30],
                counts={
                    "active_investigations": sum(1 for x in investigations if x.status == "active"),
                    "watchlists": len(watchlists),
                    "saved_searches": len(saved),
                    "scheduled_monitors": sum(1 for x in saved if x.monitor is not None and x.monitor.enabled),
                    "unacknowledged_alerts": len(alerts),
                },
            )

    async def create_investigation(
        self,
        user_id: UUID,
        command: InvestigationCreateCommand,
    ) -> InvestigationDetailView:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            row = InvestigationModel(
                owner_user_id=user_id,
                title=command.title,
                description=command.description,
                status="active",
                priority=command.priority,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.flush()
            await self._record_activity(
                session,
                row.id,
                user_id,
                action="investigation_created",
                entity_type="investigation",
                entity_id=row.id,
                summary="Created investigation.",
                metadata={"priority": command.priority},
            )
            await session.commit()
            return await self._get_investigation(session, user_id, row.id)

    async def list_investigations(self, user_id: UUID) -> list[InvestigationSummaryView]:
        async with self._session_factory() as session:
            return await self._list_investigations(session, user_id)

    async def get_investigation(self, user_id: UUID, investigation_id: UUID) -> InvestigationDetailView:
        async with self._session_factory() as session:
            return await self._get_investigation(session, user_id, investigation_id)

    async def list_investigation_members(
        self,
        user_id: UUID,
        investigation_id: UUID,
    ) -> list[InvestigationMemberView]:
        async with self._session_factory() as session:
            await self._investigation_access(session, user_id, investigation_id, minimum="reader")
            return await self._member_views(session, investigation_id)

    async def add_investigation_member(
        self,
        user_id: UUID,
        investigation_id: UUID,
        command: InvestigationMemberCreateCommand,
    ) -> InvestigationMemberView:
        async with self._session_factory() as session:
            investigation, _ = await self._investigation_access(
                session, user_id, investigation_id, minimum="owner"
            )
            email = command.email.strip().casefold()
            candidate = await session.scalar(
                select(PlatformUserModel).where(
                    func.lower(PlatformUserModel.verified_email) == email,
                    PlatformUserModel.access_status == "approved",
                )
            )
            if candidate is None:
                raise WorkspaceNotFoundError("approved analyst account not found for that email")
            if candidate.id == investigation.owner_user_id:
                raise WorkspaceConflictError("investigation owner already has full access")
            if candidate.role not in {"analyst", "source_manager", "administrator", "owner"}:
                raise WorkspaceValidationError("collaborator must have analyst workspace access")
            now = datetime.now(UTC)
            member = InvestigationMemberModel(
                investigation_id=investigation.id,
                user_id=candidate.id,
                access_role=command.access_role,
                added_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(member)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="member_added",
                entity_type="member",
                entity_id=candidate.id,
                summary=f"Added {candidate.display_name or candidate.verified_email or 'collaborator'} as {command.access_role}.",
                metadata={"access_role": command.access_role},
            )
            investigation.updated_at = now
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise WorkspaceConflictError("user is already a collaborator") from exc
            return _member_view(member, candidate)

    async def update_investigation_member(
        self,
        user_id: UUID,
        investigation_id: UUID,
        member_id: UUID,
        command: InvestigationMemberUpdateCommand,
    ) -> InvestigationMemberView:
        async with self._session_factory() as session:
            investigation, _ = await self._investigation_access(
                session, user_id, investigation_id, minimum="owner"
            )
            member = await session.scalar(
                select(InvestigationMemberModel).where(
                    InvestigationMemberModel.id == member_id,
                    InvestigationMemberModel.investigation_id == investigation.id,
                )
            )
            if member is None:
                raise WorkspaceNotFoundError("investigation collaborator not found")
            member.access_role = command.access_role
            member.updated_at = datetime.now(UTC)
            candidate = await session.get(PlatformUserModel, member.user_id)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="member_role_changed",
                entity_type="member",
                entity_id=member.user_id,
                summary=f"Changed collaborator access to {command.access_role}.",
                metadata={"access_role": command.access_role},
            )
            investigation.updated_at = datetime.now(UTC)
            await session.commit()
            return _member_view(member, candidate)

    async def remove_investigation_member(
        self,
        user_id: UUID,
        investigation_id: UUID,
        member_id: UUID,
    ) -> None:
        async with self._session_factory() as session:
            investigation, _ = await self._investigation_access(
                session, user_id, investigation_id, minimum="owner"
            )
            member = await session.scalar(
                select(InvestigationMemberModel).where(
                    InvestigationMemberModel.id == member_id,
                    InvestigationMemberModel.investigation_id == investigation.id,
                )
            )
            if member is None:
                raise WorkspaceNotFoundError("investigation collaborator not found")
            removed_user_id = member.user_id
            await session.delete(member)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="member_removed",
                entity_type="member",
                entity_id=removed_user_id,
                summary="Removed a collaborator from the investigation.",
            )
            investigation.updated_at = datetime.now(UTC)
            await session.commit()

    async def investigation_activity(
        self,
        user_id: UUID,
        investigation_id: UUID,
        *,
        limit: int = 100,
    ) -> list[InvestigationActivityView]:
        async with self._session_factory() as session:
            await self._investigation_access(session, user_id, investigation_id, minimum="reader")
            return await self._activity_views(session, investigation_id, limit=limit)

    async def investigation_manifest(
        self,
        user_id: UUID,
        investigation_id: UUID,
    ) -> InvestigationManifestView:
        async with self._session_factory() as session:
            detail = await self._get_investigation(session, user_id, investigation_id)
            snapshots: list[dict[str, object]] = []
            for item in detail.items:
                snapshot: dict[str, object] = {
                    "workspace_item_id": str(item.id),
                    "item_type": item.item_type,
                    "item_id": str(item.item_id),
                    "label": item.label,
                    "added_at": item.added_at.isoformat(),
                    "analyst_note": item.note,
                }
                if item.item_type == "event":
                    event = await session.get(EventModel, item.item_id)
                    if event is not None:
                        snapshot["event"] = {
                            "title": event.title,
                            "lifecycle_status": event.lifecycle_status,
                            "assignment_status": event.assignment_status,
                            "first_detected_at": event.first_detected_at.isoformat(),
                            "last_material_change_at": event.last_material_change_at.isoformat(),
                        }
                elif item.item_type == "article":
                    article = await session.get(ArticleModel, item.item_id)
                    if article is not None:
                        latest = await session.scalar(
                            select(ArticleVersionModel)
                            .where(ArticleVersionModel.article_id == article.id)
                            .order_by(desc(ArticleVersionModel.version_number))
                            .limit(1)
                        )
                        snapshot["article"] = {
                            "title": article.title,
                            "canonical_url": article.canonical_url,
                            "event_id": str(article.event_id),
                            "latest_version_id": str(latest.id) if latest is not None else None,
                            "latest_version_number": latest.version_number if latest is not None else None,
                            "content_sha256": latest.content_sha256 if latest is not None else None,
                            "retrieved_at": latest.retrieved_at.isoformat() if latest is not None else None,
                        }
                elif item.item_type == "claim":
                    claim = await session.get(ArticleClaimModel, item.item_id)
                    if claim is not None:
                        verification = await session.scalar(
                            select(ClaimVerificationModel)
                            .where(ClaimVerificationModel.claim_id == claim.id)
                            .order_by(desc(ClaimVerificationModel.created_at))
                            .limit(1)
                        )
                        links = list(
                            (
                                await session.scalars(
                                    select(ClaimEvidenceLinkModel)
                                    .where(ClaimEvidenceLinkModel.claim_id == claim.id)
                                    .order_by(desc(ClaimEvidenceLinkModel.retrieved_at))
                                )
                            ).all()
                        )
                        snapshot["claim"] = {
                            "claim_text": claim.claim_text,
                            "article_id": str(claim.article_id),
                            "verification": (
                                {
                                    "label": verification.label,
                                    "confidence_score": verification.confidence_score,
                                    "methodology_version": verification.methodology_version,
                                    "created_at": verification.created_at.isoformat(),
                                }
                                if verification is not None
                                else None
                            ),
                            "evidence": [
                                {
                                    "evidence_link_id": str(link.id),
                                    "source_url": link.source_url,
                                    "source_type": link.source_type,
                                    "relationship": link.relationship,
                                    "independence_score": link.independence_score,
                                    "lineage_key": link.metadata_.get("lineage_key"),
                                    "retrieved_at": link.retrieved_at.isoformat(),
                                }
                                for link in links
                            ],
                        }
                snapshots.append(snapshot)
            return InvestigationManifestView(
                investigation_id=detail.id,
                title=detail.title,
                status=detail.status,
                priority=detail.priority,
                generated_at=datetime.now(UTC),
                items=snapshots,
                notes=detail.notes,
                saved_searches=detail.saved_searches,
                members=detail.members,
            )

    async def update_investigation(
        self,
        user_id: UUID,
        investigation_id: UUID,
        command: InvestigationUpdateCommand,
    ) -> InvestigationDetailView:
        async with self._session_factory() as session:
            row, access_role = await self._investigation_access(
                session, user_id, investigation_id, minimum="editor"
            )
            if command.status is not None and access_role != "owner":
                raise WorkspacePermissionError("only the investigation owner can archive or reopen a case")
            changed: dict[str, object] = {}
            if command.title is not None and command.title != row.title:
                changed["title"] = command.title
                row.title = command.title
            if command.description is not None and command.description != row.description:
                changed["description_changed"] = True
                row.description = command.description
            if command.priority is not None and command.priority != row.priority:
                changed["priority"] = command.priority
                row.priority = command.priority
            if command.status is not None and command.status != row.status:
                changed["status"] = command.status
                row.status = command.status
            row.updated_at = datetime.now(UTC)
            if changed:
                await self._record_activity(
                    session,
                    row.id,
                    user_id,
                    action="investigation_updated",
                    entity_type="investigation",
                    entity_id=row.id,
                    summary="Updated investigation settings.",
                    metadata=changed,
                )
            await session.commit()
            return await self._get_investigation(session, user_id, row.id)

    async def add_investigation_item(
        self,
        user_id: UUID,
        investigation_id: UUID,
        command: WorkspaceItemCreateCommand,
    ) -> WorkspaceItemView:
        async with self._session_factory() as session:
            investigation, _ = await self._investigation_access(session, user_id, investigation_id, minimum="editor")
            label, metadata = await self._resolve_target(session, command.item_type, command.item_id)
            row = InvestigationItemModel(
                investigation_id=investigation.id,
                item_type=command.item_type,
                item_id=command.item_id,
                label_snapshot=label,
                note=command.note,
                added_by_user_id=user_id,
                metadata_=metadata,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            investigation.updated_at = datetime.now(UTC)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="item_added",
                entity_type=command.item_type,
                entity_id=command.item_id,
                summary=f"Added {command.item_type} to the investigation: {label}",
            )
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise WorkspaceConflictError("item is already in this investigation") from exc
            return _item_view(row)

    async def remove_investigation_item(
        self,
        user_id: UUID,
        investigation_id: UUID,
        item_id: UUID,
    ) -> None:
        async with self._session_factory() as session:
            investigation, _ = await self._investigation_access(session, user_id, investigation_id, minimum="editor")
            row = await session.scalar(
                select(InvestigationItemModel).where(
                    InvestigationItemModel.id == item_id,
                    InvestigationItemModel.investigation_id == investigation.id,
                )
            )
            if row is None:
                raise WorkspaceNotFoundError("investigation item not found")
            await session.delete(row)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="item_removed",
                entity_type=row.item_type,
                entity_id=row.item_id,
                summary=f"Removed {row.item_type} from the investigation: {row.label_snapshot}",
            )
            investigation.updated_at = datetime.now(UTC)
            await session.commit()

    async def add_note(
        self,
        user_id: UUID,
        investigation_id: UUID,
        command: AnalystNoteCreateCommand,
    ) -> AnalystNoteView:
        async with self._session_factory() as session:
            investigation, _ = await self._investigation_access(session, user_id, investigation_id, minimum="editor")
            if command.target_type != "investigation":
                if command.target_id is None:
                    raise WorkspaceValidationError("target_id is required for a targeted note")
                await self._resolve_target(session, command.target_type, command.target_id)
            elif command.target_id not in {None, investigation.id}:
                raise WorkspaceValidationError("investigation notes must target the current investigation")
            now = datetime.now(UTC)
            row = AnalystNoteModel(
                investigation_id=investigation.id,
                author_user_id=user_id,
                target_type=command.target_type,
                target_id=investigation.id if command.target_type == "investigation" else command.target_id,
                body=command.body,
                pinned=command.pinned,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="note_added",
                entity_type=command.target_type,
                entity_id=row.target_id,
                summary="Added an analyst note.",
                metadata={"pinned": command.pinned},
            )
            investigation.updated_at = now
            await session.commit()
            author = await session.get(PlatformUserModel, user_id)
            return _note_view(row, author)

    async def delete_note(self, user_id: UUID, note_id: UUID) -> None:
        async with self._session_factory() as session:
            row = await session.get(AnalystNoteModel, note_id)
            if row is None or row.investigation_id is None:
                raise WorkspaceNotFoundError("note not found")
            investigation, access_role = await self._investigation_access(
                session, user_id, row.investigation_id, minimum="reader"
            )
            if row.author_user_id != user_id and access_role != "owner":
                raise WorkspacePermissionError("only the note author or investigation owner can delete this note")
            await session.delete(row)
            await self._record_activity(
                session,
                investigation.id,
                user_id,
                action="note_deleted",
                entity_type=row.target_type,
                entity_id=row.target_id,
                summary="Deleted an analyst note.",
            )
            investigation.updated_at = datetime.now(UTC)
            await session.commit()


    async def create_saved_search(
        self,
        user_id: UUID,
        command: SavedSearchCreateCommand,
    ) -> SavedSearchView:
        async with self._session_factory() as session:
            if command.investigation_id is not None:
                await self._investigation_access(session, user_id, command.investigation_id, minimum="editor")
            now = datetime.now(UTC)
            row = SavedSearchModel(
                owner_user_id=user_id,
                investigation_id=command.investigation_id,
                name=command.name,
                query=command.query,
                filters=command.filters,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.flush()
                if command.investigation_id is not None:
                    await self._record_activity(
                        session,
                        command.investigation_id,
                        user_id,
                        action="saved_search_added",
                        entity_type="saved_search",
                        entity_id=row.id,
                        summary=f"Added saved search: {command.name}",
                    )
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise WorkspaceConflictError("a saved search with this name already exists") from exc
            owner = await session.get(PlatformUserModel, user_id)
            return _saved_search_view(row, owner=owner)

    async def delete_saved_search(self, user_id: UUID, saved_search_id: UUID) -> None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(SavedSearchModel).where(
                    SavedSearchModel.id == saved_search_id,
                    SavedSearchModel.owner_user_id == user_id,
                )
            )
            if row is None:
                raise WorkspaceNotFoundError("saved search not found")
            investigation_id = row.investigation_id
            await session.execute(
                delete(WorkspaceGeneratedAlertModel).where(
                    WorkspaceGeneratedAlertModel.owner_user_id == user_id,
                    WorkspaceGeneratedAlertModel.target_type == "saved_search",
                    WorkspaceGeneratedAlertModel.target_id == row.id,
                )
            )
            await session.execute(
                delete(WorkspaceMonitorModel).where(
                    WorkspaceMonitorModel.owner_user_id == user_id,
                    WorkspaceMonitorModel.target_type == "saved_search",
                    WorkspaceMonitorModel.target_id == row.id,
                )
            )
            await session.delete(row)
            if investigation_id is not None:
                try:
                    investigation, _ = await self._investigation_access(
                        session, user_id, investigation_id, minimum="reader"
                    )
                except WorkspaceNotFoundError:
                    investigation = None
                if investigation is not None:
                    await self._record_activity(
                        session,
                        investigation.id,
                        user_id,
                        action="saved_search_removed",
                        entity_type="saved_search",
                        entity_id=saved_search_id,
                        summary="Removed a saved search from the investigation.",
                    )
            await session.commit()

    async def set_saved_search_monitor(
        self,
        user_id: UUID,
        saved_search_id: UUID,
        command: SavedSearchMonitorCommand,
    ) -> WorkspaceMonitorView:
        async with self._session_factory() as session:
            saved = await session.scalar(
                select(SavedSearchModel).where(
                    SavedSearchModel.id == saved_search_id,
                    SavedSearchModel.owner_user_id == user_id,
                )
            )
            if saved is None:
                raise WorkspaceNotFoundError("saved search not found")
            now = datetime.now(UTC)
            monitor = await session.scalar(
                select(WorkspaceMonitorModel).where(
                    WorkspaceMonitorModel.owner_user_id == user_id,
                    WorkspaceMonitorModel.target_type == "saved_search",
                    WorkspaceMonitorModel.target_id == saved.id,
                )
            )
            if monitor is None:
                monitor = WorkspaceMonitorModel(
                    owner_user_id=user_id,
                    target_type="saved_search",
                    target_id=saved.id,
                    enabled=command.enabled,
                    cadence_minutes=command.cadence_minutes,
                    next_run_at=now,
                    last_run_at=None,
                    last_success_at=None,
                    lease_owner=None,
                    lease_version=0,
                    lease_expires_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(monitor)
            else:
                monitor.enabled = command.enabled
                monitor.cadence_minutes = command.cadence_minutes
                monitor.updated_at = now
                if command.enabled:
                    monitor.next_run_at = now
                else:
                    monitor.lease_owner = None
                    monitor.lease_expires_at = None
            if saved.investigation_id is not None:
                try:
                    investigation, _ = await self._investigation_access(
                        session, user_id, saved.investigation_id, minimum="reader"
                    )
                except WorkspaceNotFoundError:
                    investigation = None
                if investigation is not None:
                    await self._record_activity(
                        session,
                        investigation.id,
                        user_id,
                        action="saved_search_monitor_updated",
                        entity_type="saved_search",
                        entity_id=saved.id,
                        summary=(
                            f"Enabled scheduled monitoring every {command.cadence_minutes} minutes."
                            if command.enabled
                            else "Disabled scheduled monitoring."
                        ),
                        metadata={
                            "enabled": command.enabled,
                            "cadence_minutes": command.cadence_minutes,
                        },
                    )
            await session.commit()
            return _monitor_view(monitor)

    async def get_saved_search_monitor(
        self,
        user_id: UUID,
        saved_search_id: UUID,
    ) -> WorkspaceMonitorView | None:
        async with self._session_factory() as session:
            saved = await session.scalar(
                select(SavedSearchModel).where(
                    SavedSearchModel.id == saved_search_id,
                    SavedSearchModel.owner_user_id == user_id,
                )
            )
            if saved is None:
                raise WorkspaceNotFoundError("saved search not found")
            monitor = await session.scalar(
                select(WorkspaceMonitorModel).where(
                    WorkspaceMonitorModel.owner_user_id == user_id,
                    WorkspaceMonitorModel.target_type == "saved_search",
                    WorkspaceMonitorModel.target_id == saved.id,
                )
            )
            return _monitor_view(monitor) if monitor is not None else None

    async def get_saved_search_monitor_runs(
        self,
        user_id: UUID,
        saved_search_id: UUID,
        *,
        limit: int = 20,
    ) -> list[WorkspaceMonitorRunView]:
        async with self._session_factory() as session:
            saved = await session.scalar(
                select(SavedSearchModel).where(
                    SavedSearchModel.id == saved_search_id,
                    SavedSearchModel.owner_user_id == user_id,
                )
            )
            if saved is None:
                raise WorkspaceNotFoundError("saved search not found")
            monitor = await session.scalar(
                select(WorkspaceMonitorModel).where(
                    WorkspaceMonitorModel.owner_user_id == user_id,
                    WorkspaceMonitorModel.target_type == "saved_search",
                    WorkspaceMonitorModel.target_id == saved.id,
                )
            )
            if monitor is None:
                return []
            rows = list(
                (
                    await session.scalars(
                        select(WorkspaceMonitorRunModel)
                        .where(WorkspaceMonitorRunModel.monitor_id == monitor.id)
                        .order_by(desc(WorkspaceMonitorRunModel.started_at))
                        .limit(limit)
                    )
                ).all()
            )
            return [
                WorkspaceMonitorRunView(
                    id=row.id,
                    status=row.status,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    result_count=row.result_count,
                    new_result_count=row.new_result_count,
                    error=row.error,
                )
                for row in rows
            ]

    async def create_watchlist(
        self,
        user_id: UUID,
        command: WatchlistCreateCommand,
    ) -> WatchlistDetailView:
        async with self._session_factory() as session:
            now = datetime.now(UTC)
            row = WatchlistModel(
                owner_user_id=user_id,
                name=command.name,
                description=command.description,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise WorkspaceConflictError("a watchlist with this name already exists") from exc
            return WatchlistDetailView(
                id=row.id,
                name=row.name,
                description=row.description,
                items=[],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    async def delete_watchlist(self, user_id: UUID, watchlist_id: UUID) -> None:
        async with self._session_factory() as session:
            row = await self._owned_watchlist(session, user_id, watchlist_id)
            await session.execute(
                delete(WatchlistItemModel).where(WatchlistItemModel.watchlist_id == row.id)
            )
            await session.delete(row)
            await session.commit()

    async def get_watchlist(self, user_id: UUID, watchlist_id: UUID) -> WatchlistDetailView:
        async with self._session_factory() as session:
            row = await self._owned_watchlist(session, user_id, watchlist_id)
            items = list(
                (
                    await session.scalars(
                        select(WatchlistItemModel)
                        .where(WatchlistItemModel.watchlist_id == row.id)
                        .order_by(desc(WatchlistItemModel.created_at))
                    )
                ).all()
            )
            return WatchlistDetailView(
                id=row.id,
                name=row.name,
                description=row.description,
                items=[_watch_item_view(x) for x in items],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    async def add_watchlist_item(
        self,
        user_id: UUID,
        watchlist_id: UUID,
        command: WorkspaceItemCreateCommand,
    ) -> WorkspaceItemView:
        async with self._session_factory() as session:
            watchlist = await self._owned_watchlist(session, user_id, watchlist_id)
            label, metadata = await self._resolve_target(session, command.item_type, command.item_id)
            row = WatchlistItemModel(
                watchlist_id=watchlist.id,
                item_type=command.item_type,
                item_id=command.item_id,
                label_snapshot=label,
                note=command.note,
                added_by_user_id=user_id,
                metadata_=metadata,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            watchlist.updated_at = datetime.now(UTC)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise WorkspaceConflictError("item is already on this watchlist") from exc
            return _watch_item_view(row)

    async def remove_watchlist_item(
        self,
        user_id: UUID,
        watchlist_id: UUID,
        item_id: UUID,
    ) -> None:
        async with self._session_factory() as session:
            watchlist = await self._owned_watchlist(session, user_id, watchlist_id)
            row = await session.scalar(
                select(WatchlistItemModel).where(
                    WatchlistItemModel.id == item_id,
                    WatchlistItemModel.watchlist_id == watchlist.id,
                )
            )
            if row is None:
                raise WorkspaceNotFoundError("watchlist item not found")
            await session.delete(row)
            watchlist.updated_at = datetime.now(UTC)
            await session.commit()

    async def alerts(
        self,
        user_id: UUID,
        *,
        include_acknowledged: bool = False,
    ) -> list[WorkspaceAlertView]:
        async with self._session_factory() as session:
            return await self._alerts(session, user_id, include_acknowledged=include_acknowledged)

    async def acknowledge_alert(self, user_id: UUID, alert_key: str) -> None:
        if len(alert_key) > 300 or not alert_key:
            raise WorkspaceValidationError("invalid alert key")
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(WorkspaceAlertAcknowledgementModel).where(
                    WorkspaceAlertAcknowledgementModel.user_id == user_id,
                    WorkspaceAlertAcknowledgementModel.alert_key == alert_key,
                )
            )
            if existing is None:
                session.add(
                    WorkspaceAlertAcknowledgementModel(
                        user_id=user_id,
                        alert_key=alert_key,
                        acknowledged_at=datetime.now(UTC),
                    )
                )
                await session.commit()

    async def _list_investigations(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> list[InvestigationSummaryView]:
        memberships = list(
            (
                await session.scalars(
                    select(InvestigationMemberModel).where(InvestigationMemberModel.user_id == user_id)
                )
            ).all()
        )
        member_roles = {row.investigation_id: row.access_role for row in memberships}
        member_ids = list(member_roles)
        criteria = [InvestigationModel.owner_user_id == user_id]
        if member_ids:
            criteria.append(InvestigationModel.id.in_(member_ids))
        rows = list(
            (
                await session.scalars(
                    select(InvestigationModel)
                    .where(or_(*criteria))
                    .order_by(
                        (InvestigationModel.status == "active").desc(),
                        desc(InvestigationModel.updated_at),
                    )
                )
            ).all()
        )
        if not rows:
            return []
        ids = [row.id for row in rows]
        item_counts = dict(
            (
                await session.execute(
                    select(InvestigationItemModel.investigation_id, func.count())
                    .where(InvestigationItemModel.investigation_id.in_(ids))
                    .group_by(InvestigationItemModel.investigation_id)
                )
            ).all()
        )
        note_counts = dict(
            (
                await session.execute(
                    select(AnalystNoteModel.investigation_id, func.count())
                    .where(AnalystNoteModel.investigation_id.in_(ids))
                    .group_by(AnalystNoteModel.investigation_id)
                )
            ).all()
        )
        search_counts = dict(
            (
                await session.execute(
                    select(SavedSearchModel.investigation_id, func.count())
                    .where(SavedSearchModel.investigation_id.in_(ids))
                    .group_by(SavedSearchModel.investigation_id)
                )
            ).all()
        )
        member_counts = dict(
            (
                await session.execute(
                    select(InvestigationMemberModel.investigation_id, func.count())
                    .where(InvestigationMemberModel.investigation_id.in_(ids))
                    .group_by(InvestigationMemberModel.investigation_id)
                )
            ).all()
        )
        owner_ids = list({row.owner_user_id for row in rows})
        owners = list(
            (await session.scalars(select(PlatformUserModel).where(PlatformUserModel.id.in_(owner_ids)))).all()
        )
        owner_by_id = {row.id: row for row in owners}
        return [
            InvestigationSummaryView(
                id=row.id,
                owner_user_id=row.owner_user_id,
                owner_display_name=_user_label(owner_by_id.get(row.owner_user_id)),
                access_role="owner" if row.owner_user_id == user_id else member_roles[row.id],
                title=row.title,
                description=row.description,
                status=row.status,
                priority=row.priority,
                item_count=int(item_counts.get(row.id, 0)),
                note_count=int(note_counts.get(row.id, 0)),
                saved_search_count=int(search_counts.get(row.id, 0)),
                member_count=int(member_counts.get(row.id, 0)),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def _get_investigation(
        self,
        session: AsyncSession,
        user_id: UUID,
        investigation_id: UUID,
    ) -> InvestigationDetailView:
        row, access_role = await self._investigation_access(
            session, user_id, investigation_id, minimum="reader"
        )
        items = list(
            (
                await session.scalars(
                    select(InvestigationItemModel)
                    .where(InvestigationItemModel.investigation_id == row.id)
                    .order_by(desc(InvestigationItemModel.created_at))
                )
            ).all()
        )
        notes = list(
            (
                await session.scalars(
                    select(AnalystNoteModel)
                    .where(AnalystNoteModel.investigation_id == row.id)
                    .order_by(AnalystNoteModel.pinned.desc(), desc(AnalystNoteModel.created_at))
                )
            ).all()
        )
        author_ids = list({note.author_user_id for note in notes})
        note_authors = (
            list((await session.scalars(select(PlatformUserModel).where(PlatformUserModel.id.in_(author_ids)))).all())
            if author_ids
            else []
        )
        author_by_id = {author.id: author for author in note_authors}
        saved = list(
            (
                await session.scalars(
                    select(SavedSearchModel)
                    .where(SavedSearchModel.investigation_id == row.id)
                    .order_by(desc(SavedSearchModel.updated_at))
                )
            ).all()
        )
        saved_views = await self._saved_search_views(session, saved)
        owner = await session.get(PlatformUserModel, row.owner_user_id)
        members = await self._member_views(session, row.id)
        activity = await self._activity_views(session, row.id, limit=100)
        return InvestigationDetailView(
            id=row.id,
            current_user_id=user_id,
            owner_user_id=row.owner_user_id,
            owner_display_name=_user_label(owner),
            access_role=access_role,
            can_edit=_ACCESS_LEVEL[access_role] >= _ACCESS_LEVEL["editor"],
            can_manage_members=access_role == "owner",
            title=row.title,
            description=row.description,
            status=row.status,
            priority=row.priority,
            items=[_item_view(x) for x in items],
            notes=[_note_view(x, author_by_id.get(x.author_user_id)) for x in notes],
            saved_searches=saved_views,
            members=members,
            activity=activity,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _list_saved_searches(self, session: AsyncSession, user_id: UUID) -> list[SavedSearchView]:
        rows = list(
            (
                await session.scalars(
                    select(SavedSearchModel)
                    .where(SavedSearchModel.owner_user_id == user_id)
                    .order_by(desc(SavedSearchModel.updated_at))
                )
            ).all()
        )
        return await self._saved_search_views(session, rows)

    async def _saved_search_views(
        self,
        session: AsyncSession,
        rows: list[SavedSearchModel],
    ) -> list[SavedSearchView]:
        if not rows:
            return []
        owner_ids = list({row.owner_user_id for row in rows})
        owners = list(
            (await session.scalars(select(PlatformUserModel).where(PlatformUserModel.id.in_(owner_ids)))).all()
        )
        owner_by_id = {row.id: row for row in owners}
        target_ids = [row.id for row in rows]
        monitors = list(
            (
                await session.scalars(
                    select(WorkspaceMonitorModel).where(
                        WorkspaceMonitorModel.target_type == "saved_search",
                        WorkspaceMonitorModel.target_id.in_(target_ids),
                    )
                )
            ).all()
        )
        monitor_by_target = {row.target_id: row for row in monitors}
        return [
            _saved_search_view(
                row,
                owner=owner_by_id.get(row.owner_user_id),
                monitor=monitor_by_target.get(row.id),
            )
            for row in rows
        ]

    async def _list_watchlists(self, session: AsyncSession, user_id: UUID) -> list[WatchlistSummaryView]:
        rows = list(
            (
                await session.scalars(
                    select(WatchlistModel)
                    .where(WatchlistModel.owner_user_id == user_id)
                    .order_by(desc(WatchlistModel.updated_at))
                )
            ).all()
        )
        if not rows:
            return []
        ids = [row.id for row in rows]
        counts = dict(
            (
                await session.execute(
                    select(WatchlistItemModel.watchlist_id, func.count())
                    .where(WatchlistItemModel.watchlist_id.in_(ids))
                    .group_by(WatchlistItemModel.watchlist_id)
                )
            ).all()
        )
        return [
            WatchlistSummaryView(
                id=row.id,
                name=row.name,
                description=row.description,
                item_count=int(counts.get(row.id, 0)),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def _alerts(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        include_acknowledged: bool,
    ) -> list[WorkspaceAlertView]:
        watchlists = list(
            (
                await session.scalars(
                    select(WatchlistModel).where(WatchlistModel.owner_user_id == user_id)
                )
            ).all()
        )
        watchlist_ids = [row.id for row in watchlists]
        items: list[WatchlistItemModel] = []
        if watchlist_ids:
            items = list(
                (
                    await session.scalars(
                        select(WatchlistItemModel).where(WatchlistItemModel.watchlist_id.in_(watchlist_ids))
                    )
                ).all()
            )
        watched: dict[tuple[str, UUID], dict[str, object]] = {}
        for item in items:
            entry = watched.setdefault(
                (item.item_type, item.item_id),
                {"watchlist_ids": set(), "since": item.created_at, "label": item.label_snapshot},
            )
            cast_ids = entry["watchlist_ids"]
            if isinstance(cast_ids, set):
                cast_ids.add(item.watchlist_id)
            if item.created_at < entry["since"]:  # type: ignore[operator]
                entry["since"] = item.created_at

        alerts: list[WorkspaceAlertView] = []
        for (item_type, target_id), entry in watched.items():
            since = entry["since"]
            watch_ids = sorted(entry["watchlist_ids"], key=str)  # type: ignore[arg-type]
            label = str(entry["label"])
            if item_type == "event":
                event = await session.get(EventModel, target_id)
                if event is not None and event.last_material_change_at > since:  # type: ignore[operator]
                    key = f"event-change:{event.id}:{event.last_material_change_at.isoformat()}"
                    alerts.append(
                        WorkspaceAlertView(
                            alert_key=key,
                            alert_type="event_material_change",
                            severity="medium",
                            title=f"Event changed: {event.title}",
                            detail="The watched event recorded a material change after it was added to the watchlist.",
                            target_type="event",
                            target_id=event.id,
                            occurred_at=event.last_material_change_at,
                            link=f"/events/{event.id}/intelligence",
                            watchlist_ids=watch_ids,
                        )
                    )
                corrections = list(
                    (
                        await session.scalars(
                            select(ArticleCorrectionEventModel).where(
                                ArticleCorrectionEventModel.event_id == target_id,
                                ArticleCorrectionEventModel.created_at >= since,
                            )
                        )
                    ).all()
                )
                alerts.extend(_correction_alerts(corrections, "event", target_id, label, watch_ids))
            elif item_type == "article":
                corrections = list(
                    (
                        await session.scalars(
                            select(ArticleCorrectionEventModel).where(
                                ArticleCorrectionEventModel.article_id == target_id,
                                ArticleCorrectionEventModel.created_at >= since,
                            )
                        )
                    ).all()
                )
                alerts.extend(_correction_alerts(corrections, "article", target_id, label, watch_ids))
            elif item_type == "claim":
                flags = list(
                    (
                        await session.scalars(
                            select(ClaimReviewFlagModel).where(
                                ClaimReviewFlagModel.claim_id == target_id,
                                ClaimReviewFlagModel.created_at >= since,
                                ClaimReviewFlagModel.resolved_at.is_(None),
                            )
                        )
                    ).all()
                )
                for flag in flags:
                    alerts.append(
                        WorkspaceAlertView(
                            alert_key=f"claim-review:{flag.id}",
                            alert_type="claim_review_required",
                            severity=flag.severity,
                            title=f"Claim review required: {label}",
                            detail=flag.reason,
                            target_type="claim",
                            target_id=target_id,
                            occurred_at=flag.created_at,
                            link=f"/claims/{target_id}/investigation",
                            watchlist_ids=watch_ids,
                            metadata={"actions": flag.actions, "review_flag_id": str(flag.id)},
                        )
                    )
                verification = await session.scalar(
                    select(ClaimVerificationModel)
                    .where(
                        ClaimVerificationModel.claim_id == target_id,
                        ClaimVerificationModel.created_at >= since,
                    )
                    .order_by(desc(ClaimVerificationModel.created_at))
                    .limit(1)
                )
                if verification is not None:
                    alerts.append(
                        WorkspaceAlertView(
                            alert_key=f"claim-verification:{verification.id}",
                            alert_type="claim_verification_updated",
                            severity="low",
                            title=f"Claim assessment updated: {label}",
                            detail=f"Latest stored verification: {verification.label}.",
                            target_type="claim",
                            target_id=target_id,
                            occurred_at=verification.created_at,
                            link=f"/claims/{target_id}/investigation",
                            watchlist_ids=watch_ids,
                            metadata={"label": verification.label},
                        )
                    )

        generated = list(
            (
                await session.scalars(
                    select(WorkspaceGeneratedAlertModel)
                    .where(WorkspaceGeneratedAlertModel.owner_user_id == user_id)
                    .order_by(desc(WorkspaceGeneratedAlertModel.occurred_at))
                    .limit(200)
                )
            ).all()
        )
        alerts.extend(
            WorkspaceAlertView(
                alert_key=row.alert_key,
                alert_type=row.alert_type,
                severity=row.severity,
                title=row.title,
                detail=row.detail,
                target_type=row.target_type,
                target_id=row.target_id,
                occurred_at=row.occurred_at,
                link=row.link,
                watchlist_ids=[],
                metadata=row.metadata_,
            )
            for row in generated
        )

        acknowledgements = set(
            (
                await session.scalars(
                    select(WorkspaceAlertAcknowledgementModel.alert_key).where(
                        WorkspaceAlertAcknowledgementModel.user_id == user_id
                    )
                )
            ).all()
        )
        deduped: dict[str, WorkspaceAlertView] = {}
        for alert in alerts:
            alert.acknowledged = alert.alert_key in acknowledgements
            if not include_acknowledged and alert.acknowledged:
                continue
            existing = deduped.get(alert.alert_key)
            if existing is None:
                deduped[alert.alert_key] = alert
                continue
            existing.watchlist_ids = sorted(
                {*existing.watchlist_ids, *alert.watchlist_ids},
                key=str,
            )
            # A correction tied directly to an article is the most specific inspection target.
            if alert.target_type == "article" and existing.target_type != "article":
                existing.target_type = alert.target_type
                existing.target_id = alert.target_id
                existing.link = alert.link
        return sorted(deduped.values(), key=lambda x: x.occurred_at, reverse=True)

    async def _investigation_access(
        self,
        session: AsyncSession,
        user_id: UUID,
        investigation_id: UUID,
        *,
        minimum: str,
    ) -> tuple[InvestigationModel, str]:
        investigation = await session.get(InvestigationModel, investigation_id)
        if investigation is None:
            raise WorkspaceNotFoundError("investigation not found")
        if investigation.owner_user_id == user_id:
            role = "owner"
        else:
            membership = await session.scalar(
                select(InvestigationMemberModel).where(
                    InvestigationMemberModel.investigation_id == investigation_id,
                    InvestigationMemberModel.user_id == user_id,
                )
            )
            if membership is None:
                raise WorkspaceNotFoundError("investigation not found")
            role = membership.access_role
        if _ACCESS_LEVEL.get(role, 0) < _ACCESS_LEVEL[minimum]:
            raise WorkspacePermissionError(f"{minimum} access is required for this investigation")
        return investigation, role

    async def _member_views(
        self,
        session: AsyncSession,
        investigation_id: UUID,
    ) -> list[InvestigationMemberView]:
        rows = list(
            (
                await session.scalars(
                    select(InvestigationMemberModel)
                    .where(InvestigationMemberModel.investigation_id == investigation_id)
                    .order_by(InvestigationMemberModel.access_role, InvestigationMemberModel.created_at)
                )
            ).all()
        )
        if not rows:
            return []
        users = list(
            (
                await session.scalars(
                    select(PlatformUserModel).where(PlatformUserModel.id.in_([row.user_id for row in rows]))
                )
            ).all()
        )
        by_id = {user.id: user for user in users}
        return [_member_view(row, by_id.get(row.user_id)) for row in rows]

    async def _activity_views(
        self,
        session: AsyncSession,
        investigation_id: UUID,
        *,
        limit: int,
    ) -> list[InvestigationActivityView]:
        rows = list(
            (
                await session.scalars(
                    select(InvestigationActivityModel)
                    .where(InvestigationActivityModel.investigation_id == investigation_id)
                    .order_by(desc(InvestigationActivityModel.created_at))
                    .limit(limit)
                )
            ).all()
        )
        actor_ids = list({row.actor_user_id for row in rows if row.actor_user_id is not None})
        actors = (
            list((await session.scalars(select(PlatformUserModel).where(PlatformUserModel.id.in_(actor_ids)))).all())
            if actor_ids
            else []
        )
        by_id = {actor.id: actor for actor in actors}
        return [
            InvestigationActivityView(
                id=row.id,
                actor_user_id=row.actor_user_id,
                actor_display_name=_user_label(by_id.get(row.actor_user_id)) if row.actor_user_id else "System",
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                summary=row.summary,
                metadata=row.metadata_,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def _record_activity(
        self,
        session: AsyncSession,
        investigation_id: UUID,
        actor_user_id: UUID | None,
        *,
        action: str,
        entity_type: str,
        entity_id: UUID | None,
        summary: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        session.add(
            InvestigationActivityModel(
                investigation_id=investigation_id,
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
                metadata_=metadata or {},
                created_at=datetime.now(UTC),
            )
        )

    async def _owned_investigation(
        self,
        session: AsyncSession,
        user_id: UUID,
        investigation_id: UUID,
    ) -> InvestigationModel:
        row = await session.scalar(
            select(InvestigationModel).where(
                InvestigationModel.id == investigation_id,
                InvestigationModel.owner_user_id == user_id,
            )
        )
        if row is None:
            raise WorkspaceNotFoundError("investigation not found")
        return row

    async def _owned_watchlist(
        self,
        session: AsyncSession,
        user_id: UUID,
        watchlist_id: UUID,
    ) -> WatchlistModel:
        row = await session.scalar(
            select(WatchlistModel).where(
                WatchlistModel.id == watchlist_id,
                WatchlistModel.owner_user_id == user_id,
            )
        )
        if row is None:
            raise WorkspaceNotFoundError("watchlist not found")
        return row

    async def _resolve_target(
        self,
        session: AsyncSession,
        item_type: str,
        item_id: UUID,
    ) -> tuple[str, dict[str, object]]:
        if item_type == "event":
            event = await session.get(EventModel, item_id)
            if event is None:
                raise WorkspaceNotFoundError("event not found")
            return event.title, {"event_id": str(event.id)}
        if item_type == "article":
            article = await session.get(ArticleModel, item_id)
            if article is None:
                raise WorkspaceNotFoundError("article not found")
            return article.title, {"article_id": str(article.id), "event_id": str(article.event_id)}
        if item_type == "claim":
            claim = await session.get(ArticleClaimModel, item_id)
            if claim is None:
                raise WorkspaceNotFoundError("claim not found")
            article = await session.get(ArticleModel, claim.article_id)
            return claim.claim_text, {
                "claim_id": str(claim.id),
                "article_id": str(claim.article_id),
                "event_id": str(article.event_id) if article is not None else None,
            }
        raise WorkspaceValidationError(f"unsupported workspace item type: {item_type}")


def _item_view(row: InvestigationItemModel) -> WorkspaceItemView:
    return WorkspaceItemView(
        id=row.id,
        item_type=row.item_type,
        item_id=row.item_id,
        label=row.label_snapshot,
        note=row.note,
        added_at=row.created_at,
        metadata=row.metadata_,
    )


def _watch_item_view(row: WatchlistItemModel) -> WorkspaceItemView:
    return WorkspaceItemView(
        id=row.id,
        item_type=row.item_type,
        item_id=row.item_id,
        label=row.label_snapshot,
        note=row.note,
        added_at=row.created_at,
        metadata=row.metadata_,
    )


def _user_label(user: PlatformUserModel | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.verified_email


def _note_view(row: AnalystNoteModel, author: PlatformUserModel | None = None) -> AnalystNoteView:
    return AnalystNoteView(
        id=row.id,
        investigation_id=row.investigation_id,
        author_user_id=row.author_user_id,
        author_display_name=_user_label(author),
        target_type=row.target_type,
        target_id=row.target_id,
        body=row.body,
        pinned=row.pinned,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _monitor_view(row: WorkspaceMonitorModel) -> WorkspaceMonitorView:
    return WorkspaceMonitorView(
        id=row.id,
        target_type=row.target_type,
        target_id=row.target_id,
        enabled=row.enabled,
        cadence_minutes=row.cadence_minutes,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_success_at=row.last_success_at,
        lease_version=row.lease_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _saved_search_view(
    row: SavedSearchModel,
    *,
    owner: PlatformUserModel | None = None,
    monitor: WorkspaceMonitorModel | None = None,
) -> SavedSearchView:
    return SavedSearchView(
        id=row.id,
        owner_user_id=row.owner_user_id,
        owner_display_name=_user_label(owner),
        name=row.name,
        query=row.query,
        investigation_id=row.investigation_id,
        filters=row.filters,
        monitor=_monitor_view(monitor) if monitor is not None else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _member_view(
    row: InvestigationMemberModel,
    user: PlatformUserModel | None,
) -> InvestigationMemberView:
    return InvestigationMemberView(
        id=row.id,
        user_id=row.user_id,
        display_name=user.display_name if user is not None else None,
        verified_email=user.verified_email if user is not None else None,
        access_role=row.access_role,
        added_by_user_id=row.added_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _correction_alerts(
    corrections: list[ArticleCorrectionEventModel],
    target_type: str,
    target_id: UUID,
    label: str,
    watchlist_ids: list[UUID],
) -> list[WorkspaceAlertView]:
    severity_by_kind = {"retraction": "critical", "factual_correction": "high", "clarification": "medium", "update": "low"}
    rows: list[WorkspaceAlertView] = []
    for correction in corrections:
        rows.append(
            WorkspaceAlertView(
                alert_key=f"correction:{correction.id}",
                alert_type="correction_registered",
                severity=severity_by_kind.get(correction.correction_kind, "medium"),
                title=f"{correction.correction_kind.replace('_', ' ').title()}: {label}",
                detail=correction.note or "A human-confirmed correction/update was registered for watched reporting.",
                target_type=target_type,
                target_id=target_id,
                occurred_at=correction.created_at,
                link=(
                    f"/articles/{correction.article_id}/evolution"
                    if target_type == "article"
                    else f"/events/{correction.event_id}/intelligence"
                ),
                watchlist_ids=watchlist_ids,
                metadata={"correction_event_id": str(correction.id), "correction_kind": correction.correction_kind},
            )
        )
    return rows
