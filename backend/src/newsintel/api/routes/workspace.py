from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from newsintel.api.dependencies import AnalystAuth, AnalystWorkspaceServiceDependency
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
    WorkspaceAlertView,
    WorkspaceItemCreateCommand,
    WorkspaceItemView,
    WorkspaceMonitorRunView,
    WorkspaceMonitorView,
    WorkspaceOverviewView,
)
from newsintel.application.workspace_service import (
    WorkspaceConflictError,
    WorkspaceNotFoundError,
    WorkspacePermissionError,
    WorkspaceValidationError,
)

router = APIRouter(tags=["analyst-workspace"])


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, WorkspaceConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, WorkspacePermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/workspace/overview", response_model=WorkspaceOverviewView)
async def get_workspace_overview(
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WorkspaceOverviewView:
    return await service.overview(auth.id)


@router.get("/workspace/alerts", response_model=list[WorkspaceAlertView])
async def get_workspace_alerts(
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
    include_acknowledged: bool = Query(default=False),
) -> list[WorkspaceAlertView]:
    return await service.alerts(auth.id, include_acknowledged=include_acknowledged)


@router.post("/workspace/alerts/{alert_key}/acknowledge", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_workspace_alert(
    alert_key: str,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.acknowledge_alert(auth.id, alert_key)
    except WorkspaceValidationError as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/investigations", response_model=list[InvestigationSummaryView])
async def list_investigations(
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> list[InvestigationSummaryView]:
    return await service.list_investigations(auth.id)


@router.post("/investigations", response_model=InvestigationDetailView, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    command: InvestigationCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> InvestigationDetailView:
    return await service.create_investigation(auth.id, command)


@router.get("/investigations/{investigation_id}", response_model=InvestigationDetailView)
async def get_investigation(
    investigation_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> InvestigationDetailView:
    try:
        return await service.get_investigation(auth.id, investigation_id)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc


@router.get("/investigations/{investigation_id}/members", response_model=list[InvestigationMemberView])
async def list_investigation_members(
    investigation_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> list[InvestigationMemberView]:
    try:
        return await service.list_investigation_members(auth.id, investigation_id)
    except (WorkspaceNotFoundError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/investigations/{investigation_id}/members",
    response_model=InvestigationMemberView,
    status_code=status.HTTP_201_CREATED,
)
async def add_investigation_member(
    investigation_id: UUID,
    command: InvestigationMemberCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> InvestigationMemberView:
    try:
        return await service.add_investigation_member(auth.id, investigation_id, command)
    except (WorkspaceNotFoundError, WorkspacePermissionError, WorkspaceConflictError, WorkspaceValidationError) as exc:
        raise _translate_error(exc) from exc


@router.patch(
    "/investigations/{investigation_id}/members/{member_id}",
    response_model=InvestigationMemberView,
)
async def update_investigation_member(
    investigation_id: UUID,
    member_id: UUID,
    command: InvestigationMemberUpdateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> InvestigationMemberView:
    try:
        return await service.update_investigation_member(auth.id, investigation_id, member_id, command)
    except (WorkspaceNotFoundError, WorkspacePermissionError, WorkspaceValidationError) as exc:
        raise _translate_error(exc) from exc


@router.delete(
    "/investigations/{investigation_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_investigation_member(
    investigation_id: UUID,
    member_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.remove_investigation_member(auth.id, investigation_id, member_id)
    except (WorkspaceNotFoundError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/investigations/{investigation_id}/activity",
    response_model=list[InvestigationActivityView],
)
async def get_investigation_activity(
    investigation_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[InvestigationActivityView]:
    try:
        return await service.investigation_activity(auth.id, investigation_id, limit=limit)
    except (WorkspaceNotFoundError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.get("/investigations/{investigation_id}/manifest", response_model=InvestigationManifestView)
async def get_investigation_manifest(
    investigation_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> InvestigationManifestView:
    try:
        return await service.investigation_manifest(auth.id, investigation_id)
    except (WorkspaceNotFoundError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.patch("/investigations/{investigation_id}", response_model=InvestigationDetailView)
async def update_investigation(
    investigation_id: UUID,
    command: InvestigationUpdateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> InvestigationDetailView:
    try:
        return await service.update_investigation(auth.id, investigation_id, command)
    except (WorkspaceNotFoundError, WorkspaceValidationError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/investigations/{investigation_id}/items",
    response_model=WorkspaceItemView,
    status_code=status.HTTP_201_CREATED,
)
async def add_investigation_item(
    investigation_id: UUID,
    command: WorkspaceItemCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WorkspaceItemView:
    try:
        return await service.add_investigation_item(auth.id, investigation_id, command)
    except (WorkspaceNotFoundError, WorkspaceConflictError, WorkspaceValidationError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.delete("/investigations/{investigation_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_investigation_item(
    investigation_id: UUID,
    item_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.remove_investigation_item(auth.id, investigation_id, item_id)
    except (WorkspaceNotFoundError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/investigations/{investigation_id}/notes",
    response_model=AnalystNoteView,
    status_code=status.HTTP_201_CREATED,
)
async def create_investigation_note(
    investigation_id: UUID,
    command: AnalystNoteCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> AnalystNoteView:
    try:
        return await service.add_note(auth.id, investigation_id, command)
    except (WorkspaceNotFoundError, WorkspaceValidationError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investigation_note(
    note_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.delete_note(auth.id, note_id)
    except (WorkspaceNotFoundError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/saved-searches", response_model=SavedSearchView, status_code=status.HTTP_201_CREATED)
async def create_saved_search(
    command: SavedSearchCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> SavedSearchView:
    try:
        return await service.create_saved_search(auth.id, command)
    except (WorkspaceNotFoundError, WorkspaceConflictError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.get("/saved-searches/{saved_search_id}/monitor", response_model=WorkspaceMonitorView | None)
async def get_saved_search_monitor(
    saved_search_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WorkspaceMonitorView | None:
    try:
        return await service.get_saved_search_monitor(auth.id, saved_search_id)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc


@router.get(
    "/saved-searches/{saved_search_id}/monitor/runs",
    response_model=list[WorkspaceMonitorRunView],
)
async def get_saved_search_monitor_runs(
    saved_search_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[WorkspaceMonitorRunView]:
    try:
        return await service.get_saved_search_monitor_runs(auth.id, saved_search_id, limit=limit)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc


@router.put("/saved-searches/{saved_search_id}/monitor", response_model=WorkspaceMonitorView)
async def set_saved_search_monitor(
    saved_search_id: UUID,
    command: SavedSearchMonitorCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WorkspaceMonitorView:
    try:
        return await service.set_saved_search_monitor(auth.id, saved_search_id, command)
    except (WorkspaceNotFoundError, WorkspacePermissionError, WorkspaceValidationError) as exc:
        raise _translate_error(exc) from exc


@router.delete("/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_search(
    saved_search_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.delete_saved_search(auth.id, saved_search_id)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/watchlists", response_model=WatchlistDetailView, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    command: WatchlistCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WatchlistDetailView:
    try:
        return await service.create_watchlist(auth.id, command)
    except WorkspaceConflictError as exc:
        raise _translate_error(exc) from exc


@router.delete("/watchlists/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.delete_watchlist(auth.id, watchlist_id)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/watchlists/{watchlist_id}", response_model=WatchlistDetailView)
async def get_watchlist(
    watchlist_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WatchlistDetailView:
    try:
        return await service.get_watchlist(auth.id, watchlist_id)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc


@router.post(
    "/watchlists/{watchlist_id}/items",
    response_model=WorkspaceItemView,
    status_code=status.HTTP_201_CREATED,
)
async def add_watchlist_item(
    watchlist_id: UUID,
    command: WorkspaceItemCreateCommand,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> WorkspaceItemView:
    try:
        return await service.add_watchlist_item(auth.id, watchlist_id, command)
    except (WorkspaceNotFoundError, WorkspaceConflictError, WorkspaceValidationError, WorkspacePermissionError) as exc:
        raise _translate_error(exc) from exc


@router.delete("/watchlists/{watchlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watchlist_item(
    watchlist_id: UUID,
    item_id: UUID,
    auth: AnalystAuth,
    service: AnalystWorkspaceServiceDependency,
) -> Response:
    try:
        await service.remove_watchlist_item(auth.id, watchlist_id, item_id)
    except WorkspaceNotFoundError as exc:
        raise _translate_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
