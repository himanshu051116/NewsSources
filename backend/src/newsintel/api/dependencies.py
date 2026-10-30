from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from newsintel.adapters.historical.providers import (
    CommonCrawlArchiveProvider,
    GdeltDocProvider,
    GoogleFactCheckProvider,
    GuardianProvider,
    JsonHttpTransport,
    NewsApiProvider,
    NewYorkTimesProvider,
    WaybackArchiveProvider,
)
from newsintel.adapters.http.crawl_policy import CrawlPolicyHttpFetcher
from newsintel.adapters.http.safe_fetcher import SafeHttpFetcher
from newsintel.application.acquisition.polling import PollingRepository
from newsintel.application.acquisition.service import AcquisitionService
from newsintel.application.articles.query_service import ArticleQueryService
from newsintel.application.briefings.service import GroundedBriefingService
from newsintel.application.search.service import IntelligenceSearchService
from newsintel.application.search.assistance_service import SearchAssistanceService
from newsintel.application.search.rerank_service import SemanticArticleReranker, SemanticRerankConfig
from newsintel.application.search.quality_service import SearchQualityService
from newsintel.application.search.deployment_service import ProductionIntelligenceSearchService, SearchDeploymentControlService
from newsintel.adapters.semantic.local import OllamaEmbeddingClient, QdrantSemanticIndex
from newsintel.application.intelligence.entity_intelligence_service import EntityIntelligenceService
from newsintel.application.intelligence.entity_resolution_review_service import EntityResolutionReviewService
from newsintel.application.articles.verification_service import ClaimVerificationService
from newsintel.application.workspace_service import AnalystWorkspaceService
from newsintel.application.auth.dto import CurrentUser, IdentityClaims
from newsintel.application.auth.service import (
    AccessDeniedError,
    PlatformAuthService,
    assert_approved,
    assert_permission,
)
from newsintel.application.historical.internal_service import InternalHistoricalSearchService
from newsintel.application.intelligence.advanced_service import (
    EvidenceRetrievalService,
    PublisherReliabilityService,
    TemporalKnowledgeGraphService,
)
from newsintel.application.intelligence.accuracy_service import (
    ConflictResolutionService,
    EntityExternalIdentifierService,
    EvidenceOrchestrationService,
    TemporalKnowledgeResearchService,
    VerificationBenchmarkService,
)
from newsintel.application.intelligence.governance_service import (
    EntityResolutionService,
    OwnershipRegistryService,
    TemporalKnowledgeSearchService,
    VerificationCalibrationService,
)
from newsintel.application.intelligence.service import (
    CommitmentTrackingService,
    EvidenceIntelligenceService,
    HistoricalKnowledgeService,
)
from newsintel.application.intelligence.production_service import (
    ProductionReadinessService,
    VerificationManifestService,
)
from newsintel.application.intelligence.validation_service import (
    CorrectionPropagationService,
    EntityRegistryService,
    EvidenceSearchStoppingService,
    OwnershipHistoryIngestService,
    VerificationQualityGateService,
)
from newsintel.application.historical.service import HistoricalSearchService
from newsintel.application.sources.service import SourceService
from newsintel.core.config import Settings
from newsintel.core.jwt import (
    JwtValidationError,
    decode_hs256_jwt,
    decode_oidc_jwt,
)
from newsintel.domain.access import Permission
from newsintel.infrastructure.db.polling_repository import SqlAlchemyPollingRepository
from newsintel.infrastructure.db.unit_of_work import SqlAlchemyAcquisitionUnitOfWork

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(request: Request) -> PlatformAuthService:
    return PlatformAuthService(request.app.state.database.session_factory)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    service: Annotated[PlatformAuthService, Depends(get_auth_service)],
) -> CurrentUser:
    settings = request.app.state.settings
    metadata = _safe_request_metadata(request)
    try:
        if settings.dev_auth_bypass_enabled and settings.environment != "production":
            return await service.authenticate_identity(
                IdentityClaims(
                    provider=settings.dev_auth_provider,
                    provider_user_id=settings.dev_auth_user_id,
                    verified_email=settings.dev_auth_email,
                    email_verified=True,
                    display_name=settings.dev_auth_display_name,
                ),
                credential_source="development_bypass",
                request_metadata=metadata,
                bootstrap_owner_provider=settings.dev_auth_provider,
                bootstrap_owner_user_id=settings.dev_auth_user_id,
                bootstrap_owner_email=settings.dev_auth_email,
            )
        token = _token_from_request(request, credentials)
        if token is None:
            raise AccessDeniedError("missing_authentication", "authentication is required")
        if token.startswith("app:"):
            claims = _decode_app_session(token.removeprefix("app:"), settings)
            credential_source = "session_cookie"
        else:
            claims = _decode_provider_jwt(token, settings)
            credential_source = "bearer"
        provider = (
            claims.get("provider")
            if credential_source == "session_cookie"
            else settings.auth_provider_name
        )
        identity = _identity_from_claims(
            claims,
            provider=provider if isinstance(provider, str) else settings.auth_provider_name,
        )
        user = await service.authenticate_identity(
            identity,
            credential_source=credential_source,
            request_metadata=metadata,
            bootstrap_owner_provider=settings.bootstrap_owner_provider,
            bootstrap_owner_user_id=settings.bootstrap_owner_user_id,
            bootstrap_owner_email=settings.bootstrap_owner_email,
        )
        if credential_source == "session_cookie" and request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            _require_csrf(request, settings.auth_csrf_cookie_name)
        return user
    except AccessDeniedError as exc:
        raise _auth_http_error(exc) from exc
    except (JwtValidationError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_authentication",
                "message": "authentication could not be verified",
            },
        ) from exc


async def require_authenticated_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    return user


async def require_approved_user(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    try:
        assert_approved(user)
    except AccessDeniedError as exc:
        raise _auth_http_error(exc) from exc
    return user


def _permission_dependency(
    permission: Permission,
) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def dependency(
        user: Annotated[CurrentUser, Depends(require_approved_user)],
    ) -> CurrentUser:
        try:
            assert_permission(user, permission.value)
        except AccessDeniedError as exc:
            raise _auth_http_error(exc) from exc
        return user

    return dependency


def get_acquisition_service(request: Request) -> AcquisitionService:
    session_factory = request.app.state.database.session_factory
    return AcquisitionService(
        lambda: SqlAlchemyAcquisitionUnitOfWork(session_factory)
    )


def get_polling_repository(request: Request) -> PollingRepository:
    return SqlAlchemyPollingRepository(request.app.state.database.session_factory)


def get_article_query_service(request: Request) -> ArticleQueryService:
    return ArticleQueryService(request.app.state.database.session_factory)


def get_grounded_briefing_service(request: Request) -> GroundedBriefingService:
    return GroundedBriefingService(request.app.state.database.session_factory)


def get_intelligence_search_service(request: Request) -> IntelligenceSearchService:
    return IntelligenceSearchService(request.app.state.database.session_factory)


def get_search_assistance_service(request: Request) -> SearchAssistanceService:
    return SearchAssistanceService(request.app.state.database.session_factory)


def _semantic_article_reranker(request: Request) -> SemanticArticleReranker | None:
    settings = request.app.state.settings
    if not settings.semantic_search_enabled or settings.ai_provider != "local":
        return None
    return SemanticArticleReranker(
        request.app.state.database.session_factory,
        embedder=OllamaEmbeddingClient(
            base_url=settings.local_model_base_url,
            model=settings.semantic_embedding_model,
            timeout_seconds=settings.semantic_timeout_seconds,
            expected_dimension=settings.semantic_vector_size,
        ),
        index=QdrantSemanticIndex(
            base_url=settings.qdrant_url,
            collection=settings.semantic_qdrant_collection,
            timeout_seconds=settings.semantic_timeout_seconds,
        ),
        config=SemanticRerankConfig(
            model=settings.semantic_embedding_model,
            semantic_limit=settings.semantic_search_limit,
        ),
    )


def get_search_quality_service(request: Request) -> SearchQualityService:
    settings = request.app.state.settings
    semantic_reranker = _semantic_article_reranker(request)
    return SearchQualityService(
        request.app.state.database.session_factory,
        semantic_reranker=semantic_reranker,
        semantic_collection=settings.semantic_qdrant_collection if semantic_reranker else None,
    )


def get_production_intelligence_search_service(request: Request) -> ProductionIntelligenceSearchService:
    return ProductionIntelligenceSearchService(
        request.app.state.database.session_factory,
        semantic_reranker=_semantic_article_reranker(request),
    )


def get_search_deployment_control_service(request: Request) -> SearchDeploymentControlService:
    return SearchDeploymentControlService(request.app.state.database.session_factory)


def get_entity_intelligence_service(request: Request) -> EntityIntelligenceService:
    return EntityIntelligenceService(request.app.state.database.session_factory)


def get_entity_resolution_review_service(request: Request) -> EntityResolutionReviewService:
    return EntityResolutionReviewService(request.app.state.database.session_factory)


def get_claim_verification_service(request: Request) -> ClaimVerificationService:
    return ClaimVerificationService(request.app.state.database.session_factory)


def get_analyst_workspace_service(request: Request) -> AnalystWorkspaceService:
    return AnalystWorkspaceService(request.app.state.database.session_factory)


def get_internal_historical_search_service(request: Request) -> InternalHistoricalSearchService:
    return InternalHistoricalSearchService(request.app.state.database.session_factory)


def get_evidence_intelligence_service(request: Request) -> EvidenceIntelligenceService:
    return EvidenceIntelligenceService(request.app.state.database.session_factory)


def get_commitment_tracking_service(request: Request) -> CommitmentTrackingService:
    return CommitmentTrackingService(request.app.state.database.session_factory)


def get_historical_knowledge_service(request: Request) -> HistoricalKnowledgeService:
    return HistoricalKnowledgeService(request.app.state.database.session_factory)


def get_evidence_retrieval_service(request: Request) -> EvidenceRetrievalService:
    settings = request.app.state.settings
    base_fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    fetcher = CrawlPolicyHttpFetcher(
        base_fetcher,
        user_agent=settings.crawler_user_agent,
        robots_enabled=settings.crawler_robots_enabled,
        robots_cache_seconds=settings.crawler_robots_cache_seconds,
        fail_closed_on_robots_error=settings.crawler_fail_closed_on_robots_error,
        max_concurrent_per_host=settings.crawler_max_concurrent_per_host,
        min_host_interval_seconds=settings.crawler_min_host_interval_seconds,
    )
    return EvidenceRetrievalService(
        request.app.state.database.session_factory,
        fetcher,
    )


def get_evidence_orchestration_service(request: Request) -> EvidenceOrchestrationService:
    settings = request.app.state.settings
    base_fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    fetcher = CrawlPolicyHttpFetcher(
        base_fetcher,
        user_agent=settings.crawler_user_agent,
        robots_enabled=settings.crawler_robots_enabled,
        robots_cache_seconds=settings.crawler_robots_cache_seconds,
        fail_closed_on_robots_error=settings.crawler_fail_closed_on_robots_error,
        max_concurrent_per_host=settings.crawler_max_concurrent_per_host,
        min_host_interval_seconds=settings.crawler_min_host_interval_seconds,
    )
    return EvidenceOrchestrationService(request.app.state.database.session_factory, fetcher)


def get_conflict_resolution_service(request: Request) -> ConflictResolutionService:
    return ConflictResolutionService(request.app.state.database.session_factory)


def get_verification_benchmark_service(request: Request) -> VerificationBenchmarkService:
    return VerificationBenchmarkService(request.app.state.database.session_factory)


def get_entity_external_identifier_service(request: Request) -> EntityExternalIdentifierService:
    return EntityExternalIdentifierService(request.app.state.database.session_factory)


def get_temporal_knowledge_research_service(request: Request) -> TemporalKnowledgeResearchService:
    return TemporalKnowledgeResearchService(request.app.state.database.session_factory)


def get_publisher_reliability_service(request: Request) -> PublisherReliabilityService:
    return PublisherReliabilityService(request.app.state.database.session_factory)


def get_temporal_knowledge_graph_service(request: Request) -> TemporalKnowledgeGraphService:
    return TemporalKnowledgeGraphService(request.app.state.database.session_factory)


def get_ownership_registry_service(request: Request) -> OwnershipRegistryService:
    return OwnershipRegistryService(request.app.state.database.session_factory)


def get_entity_resolution_service(request: Request) -> EntityResolutionService:
    return EntityResolutionService(request.app.state.database.session_factory)


def get_verification_calibration_service(request: Request) -> VerificationCalibrationService:
    return VerificationCalibrationService(request.app.state.database.session_factory)


def get_temporal_knowledge_search_service(request: Request) -> TemporalKnowledgeSearchService:
    return TemporalKnowledgeSearchService(request.app.state.database.session_factory)


def get_evidence_search_stopping_service(request: Request) -> EvidenceSearchStoppingService:
    return EvidenceSearchStoppingService(request.app.state.database.session_factory)


def get_correction_propagation_service(request: Request) -> CorrectionPropagationService:
    return CorrectionPropagationService(request.app.state.database.session_factory)


def get_verification_quality_gate_service(request: Request) -> VerificationQualityGateService:
    return VerificationQualityGateService(request.app.state.database.session_factory)


def get_entity_registry_service(request: Request) -> EntityRegistryService:
    settings = request.app.state.settings
    base_fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    fetcher = CrawlPolicyHttpFetcher(
        base_fetcher,
        user_agent=settings.crawler_user_agent,
        robots_enabled=settings.crawler_robots_enabled,
        robots_cache_seconds=settings.crawler_robots_cache_seconds,
        fail_closed_on_robots_error=settings.crawler_fail_closed_on_robots_error,
        max_concurrent_per_host=settings.crawler_max_concurrent_per_host,
        min_host_interval_seconds=settings.crawler_min_host_interval_seconds,
    )
    return EntityRegistryService(request.app.state.database.session_factory, fetcher)


def get_ownership_history_ingest_service(request: Request) -> OwnershipHistoryIngestService:
    return OwnershipHistoryIngestService(request.app.state.database.session_factory)


def get_verification_manifest_service(request: Request) -> VerificationManifestService:
    return VerificationManifestService(request.app.state.database.session_factory)


def get_production_readiness_service(request: Request) -> ProductionReadinessService:
    return ProductionReadinessService(request.app.state.database.session_factory)


def get_source_service(request: Request) -> SourceService:
    settings = request.app.state.settings
    base_fetcher = SafeHttpFetcher(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.fetch_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
    )
    fetcher = CrawlPolicyHttpFetcher(
        base_fetcher,
        user_agent=settings.crawler_user_agent,
        robots_enabled=settings.crawler_robots_enabled,
        robots_cache_seconds=settings.crawler_robots_cache_seconds,
        fail_closed_on_robots_error=settings.crawler_fail_closed_on_robots_error,
        max_concurrent_per_host=settings.crawler_max_concurrent_per_host,
        min_host_interval_seconds=settings.crawler_min_host_interval_seconds,
    )
    return SourceService(
        session_factory=request.app.state.database.session_factory,
        fetcher=fetcher,
        max_new_urls_per_publisher_fetch=settings.max_new_urls_per_publisher_fetch,
        max_new_urls_per_fetch_job=settings.max_new_urls_per_fetch_job,
    )


async def get_historical_search_service(
    request: Request,
) -> AsyncIterator[HistoricalSearchService]:
    settings = request.app.state.settings
    transport = JsonHttpTransport(
        user_agent=settings.crawler_user_agent,
        timeout_seconds=settings.historical_provider_timeout_seconds,
    )
    max_results = settings.historical_provider_max_results
    service = HistoricalSearchService(
        providers=[
            GdeltDocProvider(transport, max_results=max_results),
            GuardianProvider(
                transport,
                api_key=settings.guardian_api_key.get_secret_value(),
                max_results=max_results,
            ),
            NewYorkTimesProvider(
                transport,
                api_key=settings.new_york_times_api_key.get_secret_value(),
                max_results=min(max_results, 10),
            ),
            NewsApiProvider(
                transport,
                api_key=settings.news_api_key.get_secret_value(),
                max_results=max_results,
            ),
            GoogleFactCheckProvider(
                transport,
                api_key=settings.google_fact_check_api_key.get_secret_value(),
                max_results=min(max_results, 50),
            ),
        ],
        archive_providers=[
            WaybackArchiveProvider(transport),
            CommonCrawlArchiveProvider(
                transport,
                collection_count=settings.common_crawl_collection_count,
            ),
        ],
        timeout_seconds=settings.historical_provider_timeout_seconds,
    )
    try:
        yield service
    finally:
        await transport.aclose()


AuthenticatedUserDependency = Annotated[
    CurrentUser,
    Depends(require_authenticated_user),
]
ApprovedUserDependency = Annotated[
    CurrentUser,
    Depends(require_approved_user),
]
ViewerAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.CONTENT_VIEW)),
]
AnalystAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.CLAIMS_VIEW)),
]
ClaimVerifierAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.CLAIMS_VERIFY)),
]
SourceManagerAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.SOURCES_MANAGE)),
]
OperationsAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.OPERATIONS_VIEW)),
]
AccessAdminAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.USERS_MANAGE)),
]
SettingsManagerAuth = Annotated[
    CurrentUser,
    Depends(_permission_dependency(Permission.SETTINGS_MANAGE)),
]
AcquisitionServiceDependency = Annotated[
    AcquisitionService,
    Depends(get_acquisition_service),
]
PollingRepositoryDependency = Annotated[
    PollingRepository,
    Depends(get_polling_repository),
]
ArticleQueryServiceDependency = Annotated[
    ArticleQueryService,
    Depends(get_article_query_service),
]
GroundedBriefingServiceDependency = Annotated[
    GroundedBriefingService,
    Depends(get_grounded_briefing_service),
]
IntelligenceSearchServiceDependency = Annotated[
    IntelligenceSearchService,
    Depends(get_intelligence_search_service),
]
ProductionIntelligenceSearchServiceDependency = Annotated[
    ProductionIntelligenceSearchService,
    Depends(get_production_intelligence_search_service),
]
SearchDeploymentControlServiceDependency = Annotated[
    SearchDeploymentControlService,
    Depends(get_search_deployment_control_service),
]
SearchAssistanceServiceDependency = Annotated[
    SearchAssistanceService,
    Depends(get_search_assistance_service),
]
SearchQualityServiceDependency = Annotated[
    SearchQualityService,
    Depends(get_search_quality_service),
]
EntityIntelligenceServiceDependency = Annotated[
    EntityIntelligenceService,
    Depends(get_entity_intelligence_service),
]
EntityResolutionReviewServiceDependency = Annotated[
    EntityResolutionReviewService,
    Depends(get_entity_resolution_review_service),
]
ClaimVerificationServiceDependency = Annotated[
    ClaimVerificationService,
    Depends(get_claim_verification_service),
]
AnalystWorkspaceServiceDependency = Annotated[
    AnalystWorkspaceService,
    Depends(get_analyst_workspace_service),
]
SourceServiceDependency = Annotated[
    SourceService,
    Depends(get_source_service),
]
HistoricalSearchServiceDependency = Annotated[
    HistoricalSearchService,
    Depends(get_historical_search_service),
]
InternalHistoricalSearchServiceDependency = Annotated[
    InternalHistoricalSearchService,
    Depends(get_internal_historical_search_service),
]
EvidenceIntelligenceServiceDependency = Annotated[
    EvidenceIntelligenceService,
    Depends(get_evidence_intelligence_service),
]
CommitmentTrackingServiceDependency = Annotated[
    CommitmentTrackingService,
    Depends(get_commitment_tracking_service),
]
HistoricalKnowledgeServiceDependency = Annotated[
    HistoricalKnowledgeService,
    Depends(get_historical_knowledge_service),
]
EvidenceRetrievalServiceDependency = Annotated[
    EvidenceRetrievalService,
    Depends(get_evidence_retrieval_service),
]
PublisherReliabilityServiceDependency = Annotated[
    PublisherReliabilityService,
    Depends(get_publisher_reliability_service),
]
TemporalKnowledgeGraphServiceDependency = Annotated[
    TemporalKnowledgeGraphService,
    Depends(get_temporal_knowledge_graph_service),
]
OwnershipRegistryServiceDependency = Annotated[
    OwnershipRegistryService,
    Depends(get_ownership_registry_service),
]
EntityResolutionServiceDependency = Annotated[
    EntityResolutionService,
    Depends(get_entity_resolution_service),
]
VerificationCalibrationServiceDependency = Annotated[
    VerificationCalibrationService,
    Depends(get_verification_calibration_service),
]
TemporalKnowledgeSearchServiceDependency = Annotated[
    TemporalKnowledgeSearchService,
    Depends(get_temporal_knowledge_search_service),
]
EvidenceOrchestrationServiceDependency = Annotated[
    EvidenceOrchestrationService,
    Depends(get_evidence_orchestration_service),
]
ConflictResolutionServiceDependency = Annotated[
    ConflictResolutionService,
    Depends(get_conflict_resolution_service),
]
VerificationBenchmarkServiceDependency = Annotated[
    VerificationBenchmarkService,
    Depends(get_verification_benchmark_service),
]
EntityExternalIdentifierServiceDependency = Annotated[
    EntityExternalIdentifierService,
    Depends(get_entity_external_identifier_service),
]
TemporalKnowledgeResearchServiceDependency = Annotated[
    TemporalKnowledgeResearchService,
    Depends(get_temporal_knowledge_research_service),
]
EvidenceSearchStoppingServiceDependency = Annotated[
    EvidenceSearchStoppingService,
    Depends(get_evidence_search_stopping_service),
]
CorrectionPropagationServiceDependency = Annotated[
    CorrectionPropagationService,
    Depends(get_correction_propagation_service),
]
VerificationQualityGateServiceDependency = Annotated[
    VerificationQualityGateService,
    Depends(get_verification_quality_gate_service),
]
EntityRegistryServiceDependency = Annotated[
    EntityRegistryService,
    Depends(get_entity_registry_service),
]
OwnershipHistoryIngestServiceDependency = Annotated[
    OwnershipHistoryIngestService,
    Depends(get_ownership_history_ingest_service),
]
VerificationManifestServiceDependency = Annotated[
    VerificationManifestService,
    Depends(get_verification_manifest_service),
]
ProductionReadinessServiceDependency = Annotated[
    ProductionReadinessService,
    Depends(get_production_readiness_service),
]
AuthServiceDependency = Annotated[
    PlatformAuthService,
    Depends(get_auth_service),
]


def _token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    cookie_value = request.cookies.get(request.app.state.settings.auth_cookie_name)
    if cookie_value:
        return f"app:{cookie_value}"
    return None


def _decode_provider_jwt(token: str, settings: Settings) -> dict[str, object]:
    issuer = settings.auth_jwt_issuer
    audience = settings.auth_jwt_audience
    algorithms = settings.auth_algorithm_list
    if not issuer or not audience:
        raise JwtValidationError("JWT issuer and audience are not configured")
    if algorithms == ["HS256"]:
        secret = settings.auth_jwt_hs256_secret.get_secret_value()
        if not secret:
            raise JwtValidationError("HS256 secret is not configured")
        return decode_hs256_jwt(
            token,
            secret=secret,
            issuer=issuer,
            audience=audience,
        )
    jwks_url = settings.auth_jwt_jwks_url
    if not jwks_url:
        raise JwtValidationError("JWKS URL is not configured")
    return decode_oidc_jwt(
        token,
        issuer=issuer,
        audience=audience,
        algorithms=list(algorithms),
        jwks_url=jwks_url,
    )


def _decode_app_session(token: str, settings: Settings) -> dict[str, object]:
    secret = settings.auth_session_secret.get_secret_value()
    if len(secret) < 32:
        raise JwtValidationError("session secret is not configured")
    return decode_hs256_jwt(
        token,
        secret=secret,
        issuer="newsintel-session",
        audience="newsintel-api",
    )


def _identity_from_claims(claims: dict[str, object], *, provider: str) -> IdentityClaims:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise JwtValidationError("token subject is missing")
    email = claims.get("email")
    verified = claims.get("email_verified")
    display_name = claims.get("name") or claims.get("user_name") or claims.get("preferred_username")
    avatar_url = claims.get("picture") or claims.get("avatar_url")
    return IdentityClaims(
        provider=provider,
        provider_user_id=subject,
        verified_email=email if isinstance(email, str) else None,
        email_verified=bool(verified),
        display_name=display_name if isinstance(display_name, str) else None,
        avatar_url=avatar_url if isinstance(avatar_url, str) else None,
    )


def _require_csrf(request: Request, csrf_cookie_name: str) -> None:
    cookie_value = request.cookies.get(csrf_cookie_name)
    header_value = request.headers.get("X-CSRF-Token")
    if not cookie_value or not header_value or cookie_value != header_value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "csrf_required",
                "message": "request could not be verified",
            },
        )


def _auth_http_error(exc: AccessDeniedError) -> HTTPException:
    status_code = (
        status.HTTP_401_UNAUTHORIZED
        if exc.code in {"missing_authentication", "invalid_authentication", "email_unverified"}
        else status.HTTP_403_FORBIDDEN
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def _safe_request_metadata(request: Request) -> dict[str, object]:
    return {
        "path": request.url.path,
        "method": request.method,
        "client_host": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:300],
        "x_request_id": getattr(request.state, "request_id", None) or request.headers.get("x-request-id"),
    }
