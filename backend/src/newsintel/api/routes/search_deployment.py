from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from newsintel.api.dependencies import (
    AnalystAuth,
    ClaimVerifierAuth,
    SearchDeploymentControlServiceDependency,
    ViewerAuth,
)
from newsintel.application.search.deployment_service import SearchDeploymentValidationError
from newsintel.application.search.dto import (
    SearchDeploymentConfigCommand,
    SearchDeploymentOutcomeCommand,
    SearchDeploymentRollbackCommand,
    SearchDeploymentStatusView,
)

router = APIRouter(tags=["search-deployment"])


@router.get("/search/deployment", response_model=SearchDeploymentStatusView)
async def search_deployment_status(
    _auth: AnalystAuth,
    service: SearchDeploymentControlServiceDependency,
) -> SearchDeploymentStatusView:
    return await service.status()


@router.put("/search/deployment", response_model=SearchDeploymentStatusView)
async def configure_search_deployment(
    command: SearchDeploymentConfigCommand,
    auth: ClaimVerifierAuth,
    service: SearchDeploymentControlServiceDependency,
) -> SearchDeploymentStatusView:
    try:
        return await service.configure(command, actor_user_id=auth.id)
    except SearchDeploymentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/search/deployment/rollback", response_model=SearchDeploymentStatusView)
async def rollback_search_deployment(
    command: SearchDeploymentRollbackCommand,
    auth: ClaimVerifierAuth,
    service: SearchDeploymentControlServiceDependency,
) -> SearchDeploymentStatusView:
    return await service.rollback(command, actor_user_id=auth.id)


@router.post("/search/deployment/outcome", status_code=status.HTTP_204_NO_CONTENT)
async def record_search_deployment_outcome(
    command: SearchDeploymentOutcomeCommand,
    auth: ViewerAuth,
    service: SearchDeploymentControlServiceDependency,
) -> None:
    recorded = await service.record_outcome(command, subject_user_id=auth.id)
    if not recorded:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="search exposure not found")
