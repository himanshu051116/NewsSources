from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from newsintel.api.dependencies import (
    AnalystAuth,
    ArticleQueryServiceDependency,
    HistoricalSearchServiceDependency,
    InternalHistoricalSearchServiceDependency,
)
from newsintel.application.articles.dto import (
    ArticleClaimHistoryView,
    ArticleVersionHistoryView,
    EventTimelineView,
)
from newsintel.application.historical.dto import (
    ArchiveLookupCommand,
    ArchiveLookupResponse,
    HistoricalSearchCommand,
    HistoricalSearchResponse,
    InternalHistoricalSearchCommand,
    InternalHistoricalSearchResponse,
)

router = APIRouter(prefix="/historical", tags=["historical intelligence"])


@router.post("/search", response_model=HistoricalSearchResponse)
async def search_historical_news(
    command: HistoricalSearchCommand,
    request: Request,
    _auth: AnalystAuth,
    service: HistoricalSearchServiceDependency,
) -> HistoricalSearchResponse:
    if not request.app.state.settings.historical_search_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="historical search is disabled",
        )
    return await service.search(command)


@router.post("/internal/search", response_model=InternalHistoricalSearchResponse)
async def search_internal_historical_corpus(
    command: InternalHistoricalSearchCommand,
    _auth: AnalystAuth,
    service: InternalHistoricalSearchServiceDependency,
) -> InternalHistoricalSearchResponse:
    return await service.search(command)


@router.post("/archives/lookup", response_model=ArchiveLookupResponse)
async def lookup_archived_url(
    command: ArchiveLookupCommand,
    request: Request,
    _auth: AnalystAuth,
    service: HistoricalSearchServiceDependency,
) -> ArchiveLookupResponse:
    if not request.app.state.settings.historical_search_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="historical search is disabled",
        )
    return await service.lookup_archives(command)

@router.get("/articles/{article_id}/versions", response_model=ArticleVersionHistoryView)
async def article_version_history(
    article_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleVersionHistoryView:
    history = await service.get_article_version_history(article_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return history


@router.get("/articles/{article_id}/claim-history", response_model=ArticleClaimHistoryView)
async def article_claim_history(
    article_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleClaimHistoryView:
    history = await service.get_article_claim_history(article_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return history


@router.get("/events/{event_id}/timeline", response_model=EventTimelineView)
async def event_timeline(
    event_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> EventTimelineView:
    timeline = await service.get_event_timeline(event_id)
    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"event not found: {event_id}",
        )
    return timeline

