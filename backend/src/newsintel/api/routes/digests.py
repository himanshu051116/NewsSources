from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from newsintel.api.dependencies import ViewerAuth
from newsintel.application.digests import (
    DigestEdition,
    DigestRequest,
    NewsDigestService,
    ReadingPreferences,
    SavedStream,
    StreamInput,
)

router = APIRouter(prefix="/api/v1", tags=["news-digests"])


def get_digest_service(request: Request) -> NewsDigestService:
    return NewsDigestService(request.app.state.database.session_factory)


DigestService = Annotated[NewsDigestService, Depends(get_digest_service)]


@router.get("/digests/preferences", response_model=ReadingPreferences)
async def get_preferences(auth: ViewerAuth, service: DigestService) -> ReadingPreferences:
    try:
        return await service.preferences(auth.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/digests/preferences", response_model=ReadingPreferences)
async def save_preferences(command: ReadingPreferences, auth: ViewerAuth,
                           service: DigestService) -> ReadingPreferences:
    try:
        return await service.save_preferences(auth.id, command)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/digests/options")
async def digest_options(auth: ViewerAuth, service: DigestService) -> dict[str, Any]:
    return await service.options()


@router.post("/digests/preview", response_model=DigestEdition)
async def preview_digest(command: DigestRequest, auth: ViewerAuth,
                         service: DigestService) -> DigestEdition:
    try:
        return await service.edition(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/digest-streams", response_model=list[SavedStream])
async def list_streams(auth: ViewerAuth, service: DigestService) -> list[SavedStream]:
    try:
        return await service.streams(auth.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/digest-streams", response_model=SavedStream, status_code=201)
async def create_stream(command: StreamInput, auth: ViewerAuth,
                        service: DigestService) -> SavedStream:
    return await _save(service, auth.id, command)


@router.put("/digest-streams/{stream_id}", response_model=SavedStream)
async def update_stream(stream_id: UUID, command: StreamInput, auth: ViewerAuth,
                        service: DigestService) -> SavedStream:
    return await _save(service, auth.id, command, stream_id)


async def _save(service: NewsDigestService, user_id: UUID, command: StreamInput,
                stream_id: UUID | None = None) -> SavedStream:
    try:
        return await service.save_stream(user_id, command, stream_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/digest-streams/{stream_id}", status_code=204)
async def delete_stream(stream_id: UUID, auth: ViewerAuth, service: DigestService) -> Response:
    try:
        await service.delete_stream(auth.id, stream_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
