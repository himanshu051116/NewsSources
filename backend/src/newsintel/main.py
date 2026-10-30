from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter

import uvicorn
from fastapi import FastAPI, Request, Response
from starlette.middleware.cors import CORSMiddleware

from newsintel import __version__
from newsintel.api.routes.access_admin import router as access_admin_router
from newsintel.api.routes.accuracy_dashboard import router as accuracy_dashboard_router
from newsintel.api.routes.acquisition import router as acquisition_router
from newsintel.api.routes.auth import router as auth_router
from newsintel.api.routes.article_intelligence_dashboard import router as article_intelligence_dashboard_router
from newsintel.api.routes.article_evolution_dashboard import router as article_evolution_dashboard_router
from newsintel.api.routes.briefing_dashboard import router as briefing_dashboard_router
from newsintel.api.routes.content import router as content_router
from newsintel.api.routes.claim_investigation_dashboard import router as claim_investigation_dashboard_router
from newsintel.api.routes.dashboard import router as dashboard_router
from newsintel.api.routes.events_dashboard import router as events_dashboard_router
from newsintel.api.routes.health import router as health_router
from newsintel.api.routes.historical import router as historical_router
from newsintel.api.routes.intelligence import router as intelligence_router
from newsintel.api.routes.news_dashboard import router as news_dashboard_router
from newsintel.api.routes.search_dashboard import router as search_dashboard_router
from newsintel.api.routes.search_quality import router as search_quality_router
from newsintel.api.routes.search_deployment import router as search_deployment_router
from newsintel.api.routes.entities import router as entities_router
from newsintel.api.routes.entity_dashboard import router as entity_dashboard_router
from newsintel.api.routes.search_quality_dashboard import router as search_quality_dashboard_router
from newsintel.api.routes.workspace import router as workspace_router
from newsintel.api.routes.workspace_dashboard import router as workspace_dashboard_router
from newsintel.api.routes.historical_dashboard import router as historical_dashboard_router
from newsintel.api.routes.pages import router as pages_router
from newsintel.api.routes.digests import router as digests_router
from newsintel.api.routes.digest_dashboard import router as digest_dashboard_router
from newsintel.api.routes.sources import router as sources_router
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.core.request_context import resolve_request_id
from newsintel.infrastructure.db.session import Database

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https: data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


async def _request_context_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = resolve_request_id(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    started = perf_counter()
    response: Response = await call_next(request)
    duration_ms = max(0.0, (perf_counter() - started) * 1000.0)
    response.headers.setdefault("X-Request-ID", request_id)
    response.headers.setdefault("Server-Timing", f"app;dur={duration_ms:.2f}")
    return response


async def _security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response: Response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    if request.url.path.startswith(("/app", "/briefs", "/admin", "/news", "/news-sources", "/historical-research", "/articles", "/events", "/claims", "/entities", "/search", "/investigations", "/watchlists", "/api/")):
        response.headers.setdefault("Cache-Control", "private, no-store")
    return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    app.state.settings = settings
    app.state.database = database
    yield
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="News Intelligence Platform API",
        version=__version__,
        description="Event-centric, evidence-backed news intelligence API",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
        openapi_url=None if settings.environment == "production" else "/openapi.json",
        lifespan=lifespan,
    )
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        )
    app.middleware("http")(_security_headers)
    app.middleware("http")(_request_context_headers)
    app.include_router(pages_router)
    app.include_router(digests_router)
    app.include_router(digest_dashboard_router)
    app.include_router(accuracy_dashboard_router)
    app.include_router(auth_router)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(access_admin_router, prefix="/api/v1")
    app.include_router(acquisition_router, prefix="/api/v1")
    app.include_router(content_router, prefix="/api/v1")
    app.include_router(search_quality_router, prefix="/api/v1")
    app.include_router(search_deployment_router, prefix="/api/v1")
    app.include_router(entities_router, prefix="/api/v1")
    app.include_router(workspace_router, prefix="/api/v1")
    app.include_router(historical_router, prefix="/api/v1")
    app.include_router(intelligence_router, prefix="/api/v1")
    app.include_router(historical_dashboard_router)
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(dashboard_router)
    app.include_router(news_dashboard_router)
    app.include_router(events_dashboard_router)
    app.include_router(search_dashboard_router)
    app.include_router(entity_dashboard_router)
    app.include_router(search_quality_dashboard_router)
    app.include_router(workspace_dashboard_router)
    app.include_router(article_intelligence_dashboard_router)
    app.include_router(article_evolution_dashboard_router)
    app.include_router(briefing_dashboard_router)
    app.include_router(claim_investigation_dashboard_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "newsintel.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
