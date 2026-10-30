from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text

from newsintel.api.dependencies import OperationsAuth
from newsintel.core.schema import (
    EXPECTED_SCHEMA_REVISION,
    REQUIRED_V25_COLUMNS,
    REQUIRED_V25_INDEXES,
    REQUIRED_V25_TABLES,
)
from newsintel.infrastructure.db.models import (
    ArticleHistoricalContextModel,
    ArticleHistoricalEnrichmentJobModel,
    ArticleIdentityModel,
    ArticleModel,
    ClaimReviewFlagModel,
    DiscoveryChannelModel,
    DerivedArtifactStateModel,
    DerivedRecomputeJobModel,
    EventBriefingJobModel,
    EventBriefingModel,
    OutboxEventModel,
    UrlCandidateModel,
    VerificationRunManifestModel,
)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str = "news-intelligence-api"


class PlatformStatusResponse(BaseModel):
    status: str
    database_revision: str | None
    article_count: int
    last_committed_article_at: datetime | None
    queue_depth: int
    oldest_pending_candidate_at: datetime | None
    candidate_stages: dict[str, int]
    pending_outbox_events: int
    open_claim_review_flags: int
    open_critical_review_flags: int
    verification_manifest_count: int
    historical_enrichment_pending: int
    historical_enrichment_failed: int
    historical_context_count: int
    historical_reconciliation_refreshes: int
    derived_recompute_pending: int
    derived_stale_artifacts: int
    articles_last_24h: int
    historical_contexts_last_24h: int
    stale_poll_leases: int
    stale_article_leases: int
    article_identity_groups: int
    briefing_pending: int
    briefing_failed: int
    briefing_count: int
    briefings_last_24h: int


@router.get("/health/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    database = request.app.state.database
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
            revision = await session.scalar(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            )
            if revision != EXPECTED_SCHEMA_REVISION:
                raise RuntimeError(
                    f"schema revision {revision!r} does not match {EXPECTED_SCHEMA_REVISION!r}"
                )
            for name in (*REQUIRED_V25_TABLES, *REQUIRED_V25_INDEXES):
                relation = await session.scalar(
                    text("SELECT to_regclass(:qualified)"),
                    {"qualified": f"public.{name}"},
                )
                if relation is None:
                    raise RuntimeError(f"required database relation is missing: {name}")
            for table_name, column_name in REQUIRED_V25_COLUMNS:
                present = await session.scalar(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:table_name "
                        "AND column_name=:column_name LIMIT 1"
                    ),
                    {"table_name": table_name, "column_name": column_name},
                )
                if present is None:
                    raise RuntimeError(
                        f"required database column is missing: {table_name}.{column_name}"
                    )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable or schema not release-ready",
        ) from exc
    return HealthResponse(status="ready")


@router.get("/status", response_model=PlatformStatusResponse)
async def platform_status(
    request: Request,
    _auth: OperationsAuth,
) -> PlatformStatusResponse:
    return await _platform_status_view(request)


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(
    request: Request,
    _auth: OperationsAuth,
) -> str:
    status_view = await _platform_status_view(request)
    lines = [
        "# HELP newsintel_articles_committed_total Stored article records.",
        "# TYPE newsintel_articles_committed_total gauge",
        f"newsintel_articles_committed_total {status_view.article_count}",
        "# HELP newsintel_queue_depth URL candidates not yet terminal.",
        "# TYPE newsintel_queue_depth gauge",
        f"newsintel_queue_depth {status_view.queue_depth}",
        "# HELP newsintel_outbox_pending_events Unpublished transactional outbox events.",
        "# TYPE newsintel_outbox_pending_events gauge",
        f"newsintel_outbox_pending_events {status_view.pending_outbox_events}",
        "# HELP newsintel_claim_review_open Claims requiring review after corrections or retractions.",
        "# TYPE newsintel_claim_review_open gauge",
        f"newsintel_claim_review_open {status_view.open_claim_review_flags}",
        "# HELP newsintel_claim_review_critical_open Critical claims requiring review after retractions.",
        "# TYPE newsintel_claim_review_critical_open gauge",
        f"newsintel_claim_review_critical_open {status_view.open_critical_review_flags}",
        "# HELP newsintel_verification_manifests_total Reproducibility manifests stored for verification revisions.",
        "# TYPE newsintel_verification_manifests_total gauge",
        f"newsintel_verification_manifests_total {status_view.verification_manifest_count}",
        "# HELP newsintel_historical_enrichment_pending Article versions waiting for historical enrichment.",
        "# TYPE newsintel_historical_enrichment_pending gauge",
        f"newsintel_historical_enrichment_pending {status_view.historical_enrichment_pending}",
        "# HELP newsintel_historical_enrichment_failed Historical enrichment jobs in terminal failure state.",
        "# TYPE newsintel_historical_enrichment_failed gauge",
        f"newsintel_historical_enrichment_failed {status_view.historical_enrichment_failed}",
        "# HELP newsintel_historical_contexts_total Persisted article historical-context records.",
        "# TYPE newsintel_historical_contexts_total gauge",
        f"newsintel_historical_contexts_total {status_view.historical_context_count}",
        "# HELP newsintel_historical_reconciliation_refreshes_total Historical contexts requeued because older same-event reporting arrived late.",
        "# TYPE newsintel_historical_reconciliation_refreshes_total gauge",
        f"newsintel_historical_reconciliation_refreshes_total {status_view.historical_reconciliation_refreshes}",
        "# HELP newsintel_derived_recompute_pending Derived-artifact recompute jobs pending execution.",
        "# TYPE newsintel_derived_recompute_pending gauge",
        f"newsintel_derived_recompute_pending {status_view.derived_recompute_pending}",
        "# HELP newsintel_derived_stale_artifacts Derived intelligence artifacts currently marked stale.",
        "# TYPE newsintel_derived_stale_artifacts gauge",
        f"newsintel_derived_stale_artifacts {status_view.derived_stale_artifacts}",
        "# HELP newsintel_event_briefing_pending Event briefings queued/retrying/running.",
        "# TYPE newsintel_event_briefing_pending gauge",
        f"newsintel_event_briefing_pending {status_view.briefing_pending}",
        "# HELP newsintel_event_briefing_failed Event briefing jobs in terminal failure state.",
        "# TYPE newsintel_event_briefing_failed gauge",
        f"newsintel_event_briefing_failed {status_view.briefing_failed}",
        "# HELP newsintel_event_briefings_total Persisted grounded event briefings.",
        "# TYPE newsintel_event_briefings_total gauge",
        f"newsintel_event_briefings_total {status_view.briefing_count}",
        "# HELP newsintel_candidate_stage_count URL candidates by processing stage.",
        "# TYPE newsintel_candidate_stage_count gauge",
    ]
    for stage, count in sorted(status_view.candidate_stages.items()):
        escaped_stage = stage.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'newsintel_candidate_stage_count{{stage="{escaped_stage}"}} {count}')
    return "\n".join(lines) + "\n"


async def _platform_status_view(request: Request) -> PlatformStatusResponse:
    database = request.app.state.database
    async with database.session_factory() as session:
        revision = await session.scalar(
            text(
                "SELECT version_num FROM alembic_version "
                "ORDER BY version_num DESC LIMIT 1"
            )
        )
        article_count = int(
            await session.scalar(select(func.count(ArticleModel.id))) or 0
        )
        last_committed_article_at = await session.scalar(
            select(func.max(ArticleModel.created_at))
        )
        queue_depth = int(
            await session.scalar(
                select(func.count(UrlCandidateModel.id)).where(
                    UrlCandidateModel.processing_stage.in_(
                        [
                            "queued",
                            "leased",
                            "fetching",
                            "fetched",
                            "extracting",
                            "extracted",
                            "validated",
                            "persisting",
                            "retryable_failure",
                        ]
                    )
                )
            )
            or 0
        )
        oldest_pending_candidate_at = await session.scalar(
            select(func.min(UrlCandidateModel.first_discovered_at)).where(
                UrlCandidateModel.processing_stage.in_(
                    [
                        "queued",
                        "leased",
                        "fetching",
                        "fetched",
                        "extracting",
                        "extracted",
                        "validated",
                        "persisting",
                        "retryable_failure",
                    ]
                )
            )
        )
        stage_rows = (
            await session.execute(
                select(
                    UrlCandidateModel.processing_stage,
                    func.count(UrlCandidateModel.id),
                ).group_by(UrlCandidateModel.processing_stage)
            )
        ).all()
        pending_outbox_events = int(
            await session.scalar(
                select(func.count(OutboxEventModel.id)).where(
                    OutboxEventModel.published_at.is_(None)
                )
            )
            or 0
        )
        open_claim_review_flags = int(
            await session.scalar(
                select(func.count(ClaimReviewFlagModel.id)).where(
                    ClaimReviewFlagModel.state == "review_required"
                )
            )
            or 0
        )
        open_critical_review_flags = int(
            await session.scalar(
                select(func.count(ClaimReviewFlagModel.id)).where(
                    ClaimReviewFlagModel.state == "review_required",
                    ClaimReviewFlagModel.severity == "critical",
                )
            )
            or 0
        )
        verification_manifest_count = int(
            await session.scalar(select(func.count(VerificationRunManifestModel.id))) or 0
        )
        historical_enrichment_pending = int(
            await session.scalar(
                select(func.count(ArticleHistoricalEnrichmentJobModel.id)).where(
                    ArticleHistoricalEnrichmentJobModel.state.in_(["queued", "retry", "running"])
                )
            )
            or 0
        )
        historical_enrichment_failed = int(
            await session.scalar(
                select(func.count(ArticleHistoricalEnrichmentJobModel.id)).where(
                    ArticleHistoricalEnrichmentJobModel.state == "failed"
                )
            )
            or 0
        )
        historical_context_count = int(
            await session.scalar(select(func.count(ArticleHistoricalContextModel.id))) or 0
        )
        historical_reconciliation_refreshes = int(
            await session.scalar(
                select(func.coalesce(func.sum(ArticleHistoricalEnrichmentJobModel.refresh_count), 0))
            )
            or 0
        )
        derived_recompute_pending = int(
            await session.scalar(
                select(func.count(DerivedRecomputeJobModel.id)).where(
                    DerivedRecomputeJobModel.state.in_(["queued", "retry", "leased"])
                )
            )
            or 0
        )
        derived_stale_artifacts = int(
            await session.scalar(
                select(func.count(DerivedArtifactStateModel.id)).where(
                    DerivedArtifactStateModel.stale.is_(True)
                )
            )
            or 0
        )
        now = datetime.now(UTC)
        since_24h = now - timedelta(hours=24)
        articles_last_24h = int(
            await session.scalar(
                select(func.count(ArticleModel.id)).where(ArticleModel.created_at >= since_24h)
            )
            or 0
        )
        historical_contexts_last_24h = int(
            await session.scalar(
                select(func.count(ArticleHistoricalContextModel.id)).where(
                    ArticleHistoricalContextModel.generated_at >= since_24h
                )
            )
            or 0
        )
        stale_poll_leases = int(
            await session.scalar(
                select(func.count(DiscoveryChannelModel.id)).where(
                    DiscoveryChannelModel.lease_owner.is_not(None),
                    DiscoveryChannelModel.lease_expires_at < now,
                )
            )
            or 0
        )
        stale_article_leases = int(
            await session.scalar(
                select(func.count(UrlCandidateModel.id)).where(
                    UrlCandidateModel.state == "leased",
                    UrlCandidateModel.lease_expires_at < now,
                )
            )
            or 0
        )
        article_identity_groups = int(
            await session.scalar(select(func.count(ArticleIdentityModel.id))) or 0
        )
        briefing_pending = int(
            await session.scalar(select(func.count(EventBriefingJobModel.id)).where(
                EventBriefingJobModel.state.in_(["queued", "retry", "running"])
            )) or 0
        )
        briefing_failed = int(
            await session.scalar(select(func.count(EventBriefingJobModel.id)).where(
                EventBriefingJobModel.state == "failed"
            )) or 0
        )
        briefing_count = int(await session.scalar(select(func.count(EventBriefingModel.id))) or 0)
        briefings_last_24h = int(
            await session.scalar(select(func.count(EventBriefingModel.id)).where(
                EventBriefingModel.generated_at >= since_24h
            )) or 0
        )
    return PlatformStatusResponse(
        status="ok",
        database_revision=str(revision) if revision else None,
        article_count=article_count,
        last_committed_article_at=last_committed_article_at,
        queue_depth=queue_depth,
        oldest_pending_candidate_at=oldest_pending_candidate_at,
        candidate_stages={str(stage): int(count) for stage, count in stage_rows},
        pending_outbox_events=pending_outbox_events,
        open_claim_review_flags=open_claim_review_flags,
        open_critical_review_flags=open_critical_review_flags,
        verification_manifest_count=verification_manifest_count,
        historical_enrichment_pending=historical_enrichment_pending,
        historical_enrichment_failed=historical_enrichment_failed,
        historical_context_count=historical_context_count,
        historical_reconciliation_refreshes=historical_reconciliation_refreshes,
        derived_recompute_pending=derived_recompute_pending,
        derived_stale_artifacts=derived_stale_artifacts,
        articles_last_24h=articles_last_24h,
        historical_contexts_last_24h=historical_contexts_last_24h,
        stale_poll_leases=stale_poll_leases,
        stale_article_leases=stale_article_leases,
        article_identity_groups=article_identity_groups,
        briefing_pending=briefing_pending,
        briefing_failed=briefing_failed,
        briefing_count=briefing_count,
        briefings_last_24h=briefings_last_24h,
    )
