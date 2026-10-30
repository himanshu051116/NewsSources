import asyncio
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from newsintel.api.dependencies import (
    AnalystAuth,
    ArticleQueryServiceDependency,
    GroundedBriefingServiceDependency,
    ProductionIntelligenceSearchServiceDependency,
    SearchAssistanceServiceDependency,
    ClaimVerificationServiceDependency,
    ClaimVerifierAuth,
    ViewerAuth,
)
from newsintel.application.articles.dto import (
    ArticleClaimView,
    ArticleDetailView,
    ArticleHistoricalContextView,
    ArticleIntelligenceStateView,
    ArticleQualityProfileView,
    ArticleSummaryView,
    ClaimInvestigationView,
    ClaimVerificationExecutionView,
    ClaimVerificationRecomputeCommand,
    EventDetailView,
    EventDossierView,
    EventSummaryView,
    IntelligenceSearchView,
)

from newsintel.domain.access import Permission
from newsintel.application.search.assistance_dto import SearchAssistanceView
from newsintel.application.search.service import InvalidSearchCursorError, SearchFilters

router = APIRouter(tags=["content"])


@router.get("/articles", response_model=list[ArticleSummaryView])
async def list_articles(
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    before_observed_at: datetime | None = None,
    before_id: UUID | None = None,
) -> list[ArticleSummaryView]:
    if (before_observed_at is None) != (before_id is None):
        raise HTTPException(status_code=422, detail="Both before_observed_at and before_id are required for older pages")
    if before_observed_at is not None and before_observed_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="before_observed_at must include a timezone")
    if before_id is not None and offset:
        raise HTTPException(status_code=422, detail="Do not combine older-page cursor and offset")
    return await service.list_articles(
        limit=limit, offset=offset, before_observed_at=before_observed_at, before_id=before_id,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetailView)
async def get_article(
    article_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleDetailView:
    article = await service.get_article(article_id)
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return article


@router.get(
    "/articles/{article_id}/intelligence-state",
    response_model=ArticleIntelligenceStateView,
)
async def get_article_intelligence_state(
    article_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleIntelligenceStateView:
    state_view = await service.get_article_intelligence_state(article_id)
    if state_view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return state_view


@router.get("/articles/{article_id}/intelligence-stream")
async def stream_article_intelligence_state(
    article_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> StreamingResponse:
    async def events():
        last_payload: str | None = None
        # Keep each connection bounded. The browser reconnects automatically if
        # an article remains open for longer than this window.
        for _ in range(90):
            state_view = await service.get_article_intelligence_state(article_id)
            if state_view is None:
                yield 'event: missing\ndata: {"detail":"article not found"}\n\n'
                return
            payload = state_view.model_dump_json()
            if payload != last_payload:
                yield f"event: intelligence_state\ndata: {payload}\n\n"
                last_payload = payload
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/articles/{article_id}/historical-context",
    response_model=ArticleHistoricalContextView,
)
async def get_article_historical_context(
    article_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleHistoricalContextView:
    context = await service.get_article_historical_context(article_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"historical context not available for article: {article_id}",
        )
    return context


@router.get("/articles/{article_id}/claims", response_model=list[ArticleClaimView])
async def get_article_claims(
    article_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> list[ArticleClaimView]:
    claims = await service.get_article_claims(article_id)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return claims


@router.post("/claims/{claim_id}/verify", response_model=ClaimVerificationExecutionView)
async def recompute_claim_verification(
    claim_id: UUID,
    command: ClaimVerificationRecomputeCommand,
    _auth: ClaimVerifierAuth,
    service: ClaimVerificationServiceDependency,
) -> ClaimVerificationExecutionView:
    result = await service.recompute(
        claim_id,
        retrieval_complete=command.retrieval_complete,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"claim not found: {claim_id}",
        )
    return result


@router.get("/articles/{article_id}/quality", response_model=ArticleQualityProfileView)
async def get_article_quality(
    article_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> ArticleQualityProfileView:
    profile = await service.get_article_quality(article_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"article not found: {article_id}",
        )
    return profile


@router.get("/search", response_model=IntelligenceSearchView)
async def search_intelligence(
    q: str,
    auth: ViewerAuth,
    service: ProductionIntelligenceSearchServiceDependency,
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=1200),
    result_type: str = Query(default="all", pattern="^(all|event|article|claim|entity)$"),
    language: str | None = Query(default=None, min_length=1, max_length=35),
    publisher: str | None = Query(default=None, min_length=1, max_length=200),
    lifecycle_status: str | None = Query(default=None, min_length=1, max_length=40),
    from_date: datetime | None = Query(default=None),
    to_date: datetime | None = Query(default=None),
    limit_per_type: int | None = Query(default=None, ge=1, le=40, deprecated=True),
) -> IntelligenceSearchView:
    normalized = q.strip()
    include_claims = Permission.CLAIMS_VIEW.value in auth.permissions
    include_entities = Permission.CLAIMS_VIEW.value in auth.permissions
    effective_limit = min(100, max(1, (limit_per_type * 3) if limit_per_type is not None else limit))
    filters = SearchFilters(
        result_type=result_type,
        language=language,
        publisher=publisher,
        lifecycle_status=lifecycle_status,
        from_date=from_date,
        to_date=to_date,
    )
    try:
        return await service.search(
            subject_user_id=auth.id,
            query=normalized,
            limit=effective_limit,
            include_claims=include_claims,
            include_entities=include_entities,
            filters=filters,
            cursor=cursor,
        )
    except (InvalidSearchCursorError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/search/assist", response_model=SearchAssistanceView)
async def assist_search_query(
    q: str,
    auth: ViewerAuth,
    service: SearchAssistanceServiceDependency,
    limit: int = Query(default=6, ge=1, le=12),
) -> SearchAssistanceView:
    return await service.suggest(
        q,
        limit=limit,
        include_entities=Permission.CLAIMS_VIEW.value in auth.permissions,
    )


@router.get("/claims/{claim_id}/dossier", response_model=ClaimInvestigationView)
async def get_claim_investigation(
    claim_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> ClaimInvestigationView:
    dossier = await service.get_claim_investigation(claim_id)
    if dossier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"claim not found: {claim_id}",
        )
    return dossier


@router.get("/events", response_model=list[EventSummaryView])
async def list_events(
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1_000_000),
    query: str | None = Query(default=None, min_length=1, max_length=240),
    lifecycle_status: str | None = Query(default=None, max_length=40),
) -> list[EventSummaryView]:
    return await service.list_events(
        limit=limit,
        offset=offset,
        query=query,
        lifecycle_status=lifecycle_status,
    )


@router.get("/events/{event_id}", response_model=EventDetailView)
async def get_event(
    event_id: UUID,
    _auth: ViewerAuth,
    service: ArticleQueryServiceDependency,
) -> EventDetailView:
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"event not found: {event_id}",
        )
    return event


@router.get("/events/{event_id}/dossier", response_model=EventDossierView)
async def get_event_dossier(
    event_id: UUID,
    _auth: AnalystAuth,
    service: ArticleQueryServiceDependency,
) -> EventDossierView:
    dossier = await service.get_event_dossier(event_id)
    if dossier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"event not found: {event_id}",
        )
    return dossier


@router.get("/events/{event_id}/briefing")
async def get_event_briefing(
    event_id: UUID,
    _auth: AnalystAuth,
    service: GroundedBriefingServiceDependency,
) -> dict[str, object]:
    briefing = await service.latest(event_id)
    if briefing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="briefing not generated yet")
    return {
        "id": str(briefing.id),
        "event_id": str(briefing.event_id),
        "trigger_article_version_id": str(briefing.trigger_article_version_id),
        "methodology_version": briefing.methodology_version,
        "evidence_pack_sha256": briefing.evidence_pack_sha256,
        "payload": briefing.payload,
        "evidence_refs": briefing.evidence_refs,
        "generated_at": briefing.generated_at.isoformat(),
    }


@router.post("/events/{event_id}/briefing/rebuild")
async def rebuild_event_briefing(
    event_id: UUID,
    _auth: AnalystAuth,
    service: GroundedBriefingServiceDependency,
) -> dict[str, object]:
    payload = await service.rebuild_now(event_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event has no article versions")
    return payload
