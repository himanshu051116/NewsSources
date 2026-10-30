from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from newsintel.api.dependencies import (
    AnalystAuth,
    ClaimVerifierAuth,
    EntityIntelligenceServiceDependency,
    EntityResolutionReviewServiceDependency,
)
from newsintel.application.intelligence.entity_intelligence_dto import (
    EntityConflictScanView,
    EntityMentionRefreshView,
    EntityMergeCommand,
    EntityProfileView,
    EntityResolutionActionView,
    EntityResolutionCandidateView,
    EntityResolutionRationaleCommand,
    EntitySearchView,
    EntitySplitAliasCommand,
)

router = APIRouter(tags=["entities"])


@router.get("/entities/search", response_model=EntitySearchView)
async def search_entities(
    q: str,
    _auth: AnalystAuth,
    service: EntityIntelligenceServiceDependency,
    entity_type: str | None = Query(default=None, max_length=60),
    country_code: str | None = Query(default=None, max_length=8),
    limit: int = Query(default=30, ge=1, le=100),
) -> EntitySearchView:
    try:
        return await service.search(q, entity_type=entity_type, country_code=country_code, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# Static entity-resolution routes intentionally precede /entities/{entity_id}/... routes.
@router.post("/entities/resolution/scan", response_model=EntityConflictScanView)
async def scan_entity_resolution_conflicts(
    _auth: ClaimVerifierAuth,
    service: EntityResolutionReviewServiceDependency,
    limit: int = Query(default=500, ge=1, le=5_000),
) -> EntityConflictScanView:
    return await service.scan_conflicts(limit=limit)


@router.get("/entities/resolution/candidates", response_model=list[EntityResolutionCandidateView])
async def list_entity_resolution_candidates(
    _auth: AnalystAuth,
    service: EntityResolutionReviewServiceDependency,
    candidate_status: str = Query(default="pending", alias="status", max_length=24),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EntityResolutionCandidateView]:
    try:
        return await service.list_candidates(status=candidate_status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/entities/resolution/candidates/{candidate_id}/reject", response_model=EntityResolutionActionView)
async def reject_entity_resolution_candidate(
    candidate_id: UUID,
    command: EntityResolutionRationaleCommand,
    auth: ClaimVerifierAuth,
    service: EntityResolutionReviewServiceDependency,
) -> EntityResolutionActionView:
    try:
        result = await service.reject_candidate(candidate_id, actor_user_id=auth.id, rationale=command.rationale)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resolution candidate not found")
    return result


@router.post("/entities/resolution/merge", response_model=EntityResolutionActionView)
async def merge_entities(
    command: EntityMergeCommand,
    auth: ClaimVerifierAuth,
    service: EntityResolutionReviewServiceDependency,
) -> EntityResolutionActionView:
    try:
        return await service.merge(command, actor_user_id=auth.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/entities/resolution/actions", response_model=list[EntityResolutionActionView])
async def entity_resolution_history(
    _auth: AnalystAuth,
    service: EntityResolutionReviewServiceDependency,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EntityResolutionActionView]:
    return await service.history(limit=limit)


@router.get("/entities/{entity_id}/profile", response_model=EntityProfileView)
async def entity_profile(
    entity_id: UUID,
    _auth: AnalystAuth,
    service: EntityIntelligenceServiceDependency,
    mention_limit: int = Query(default=50, ge=1, le=200),
) -> EntityProfileView:
    result = await service.profile(entity_id, mention_limit=mention_limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return result


@router.post("/entities/{entity_id}/refresh-mentions", response_model=EntityMentionRefreshView)
async def refresh_entity_mentions(
    entity_id: UUID,
    _auth: ClaimVerifierAuth,
    service: EntityIntelligenceServiceDependency,
) -> EntityMentionRefreshView:
    try:
        result = await service.refresh_mentions(entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return result


@router.post("/entities/{entity_id}/split-alias", response_model=EntityResolutionActionView)
async def split_entity_alias(
    entity_id: UUID,
    command: EntitySplitAliasCommand,
    auth: ClaimVerifierAuth,
    service: EntityResolutionReviewServiceDependency,
) -> EntityResolutionActionView:
    try:
        return await service.split_alias(entity_id, command, actor_user_id=auth.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
