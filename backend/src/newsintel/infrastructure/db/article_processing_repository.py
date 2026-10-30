from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import structlog
from sqlalchemy import and_, case, desc, func, nullslast, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.artifacts.local_store import RawFetchArtifact
from newsintel.adapters.extractors.article_html import ExtractedArticle
from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.articles.processing import (
    ArticleFetchRun,
    ArticleFetchRunStatus,
    ArticleProcessingRepository,
    ArticleProcessingResult,
    ArticleProcessingStage,
    LeasedUrlCandidate,
    UrlCandidateState,
)
from newsintel.contracts.events import IntegrationEvent
from newsintel.core.ids import uuid7
from newsintel.domain.events.assignment import (
    EventAssignmentDecision,
    EventAssignmentState,
    decide_event_assignment,
)
from newsintel.domain.events.matching import (
    POLICY_VERSION as MATCHING_POLICY_VERSION,
)
from newsintel.domain.events.matching import (
    ArticleEventProfile,
    EventReference,
    build_event_candidates,
    event_candidate_features,
    provisional_event_features,
    top_terms,
)
from newsintel.domain.intelligence.document_provenance import locate_pdf_source_sentence
from newsintel.domain.intelligence.claims import (
    CLAIM_EXTRACTOR_VERSION,
    ClaimVerificationLabel,
    extract_claims,
)
from newsintel.domain.intelligence.digest_quality import prepare_excerpt
from newsintel.domain.intelligence.lineage import (
    estimate_lineage_similarity,
    fingerprint_content,
    fingerprint_from_metadata,
    fingerprint_metadata,
)
from newsintel.infrastructure.db.acquisition_maintenance import pause_disabled_candidates
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleFetchRunModel,
    ArticleHistoricalEnrichmentJobModel,
    ArticleIdentityMemberModel,
    ArticleIdentityModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimEvidenceLinkModel,
    ClaimVerificationModel,
    EventAssignmentModel,
    EventModel,
    OutboxEventModel,
    PublisherModel,
    SourceCandidateModel,
    UrlCandidateModel,
)

logger = structlog.get_logger(__name__)


class SqlAlchemyArticleProcessingRepository(ArticleProcessingRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def lease_due_candidates(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> tuple[LeasedUrlCandidate, ...]:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        async with self._session_factory() as session, session.begin():
            await pause_disabled_candidates(session, now)
            eligible = or_(
                and_(UrlCandidateModel.state.in_(["ready", "retry"]),
                     UrlCandidateModel.next_fetch_at <= now),
                and_(UrlCandidateModel.state == "leased",
                     or_(UrlCandidateModel.lease_expires_at < now,
                         UrlCandidateModel.lease_expires_at.is_(None))),
            )
            recovery_priority = case((UrlCandidateModel.state == "leased", 0), else_=1)
            ranked = (select(UrlCandidateModel.id, func.row_number().over(
                partition_by=UrlCandidateModel.publisher_id,
                order_by=(recovery_priority, nullslast(desc(UrlCandidateModel.published_at)),
                          nullslast(desc(UrlCandidateModel.first_discovered_at)),
                          desc(UrlCandidateModel.priority_score), UrlCandidateModel.id),
            ).label("publisher_rank"))
                .join(PublisherModel, PublisherModel.id == UrlCandidateModel.publisher_id)
                .where(PublisherModel.active.is_(True), eligible).subquery())
            rows = (
                await session.scalars(
                    select(UrlCandidateModel)
                    .join(ranked, ranked.c.id == UrlCandidateModel.id)
                    .order_by(
                        ranked.c.publisher_rank,
                        recovery_priority,
                        nullslast(desc(UrlCandidateModel.published_at)),
                        nullslast(desc(UrlCandidateModel.first_discovered_at)),
                        desc(UrlCandidateModel.priority_score),
                        UrlCandidateModel.next_fetch_at,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True, of=UrlCandidateModel)
                )
            ).all()
            leased: list[LeasedUrlCandidate] = []
            for row in rows:
                row.state = UrlCandidateState.LEASED.value
                row.processing_stage = ArticleProcessingStage.LEASED.value
                row.lease_owner = worker_id
                row.lease_version = int(row.lease_version or 0) + 1
                row.lease_heartbeat_at = now
                row.lease_expires_at = lease_expires_at
                row.current_worker = worker_id
                row.attempt_count += 1
                row.processing_started_at = now
                row.processing_completed_at = None
                row.processing_duration_ms = None
                row.last_failure_code = None
                row.last_failure_message = None
                _mark_stage(row, ArticleProcessingStage.LEASED, now)
                row.updated_at = now
                leased.append(
                    LeasedUrlCandidate(
                        id=row.id,
                        publisher_id=row.publisher_id,
                        normalized_url=row.normalized_url,
                        attempt_count=row.attempt_count,
                        published_at=row.published_at,
                        first_discovered_at=row.first_discovered_at,
                        url_type=row.url_type,
                        lease_version=row.lease_version,
                        fetch_job_id=row.originating_fetch_job_id,
                        lease_owner=worker_id,
                    )
                )
            return tuple(leased)

    async def start_fetch(
        self,
        *,
        candidate_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
        lease_version: int = 0,
    ) -> ArticleFetchRun:
        async with self._session_factory() as session, session.begin():
            candidate_row = await session.get(UrlCandidateModel, candidate_id, with_for_update=True)
            if (
                candidate_row is None or candidate_row.lease_owner != worker_id
                or candidate_row.lease_version != lease_version
                or candidate_row.state != UrlCandidateState.LEASED.value
                or candidate_row.lease_expires_at is None
                or candidate_row.lease_expires_at <= datetime.now(UTC)
            ):
                raise RuntimeError("article lease lost before fetch start")
            run = ArticleFetchRun(
                id=uuid7(),
                candidate_id=candidate_id,
                worker_id=worker_id,
                trace_id=trace_id,
                started_at=started_at,
                lease_version=candidate_row.lease_version,
                fetch_job_id=candidate_row.originating_fetch_job_id,
            )
            session.add(
                ArticleFetchRunModel(
                    id=run.id,
                    candidate_id=run.candidate_id,
                    worker_id=run.worker_id,
                    trace_id=run.trace_id,
                    status=ArticleFetchRunStatus.RUNNING.value,
                    started_at=run.started_at,
                    fetch_job_id=run.fetch_job_id,
                    lease_version=run.lease_version,
                )
            )
            if candidate_row is not None:
                candidate_row.processing_stage = ArticleProcessingStage.FETCHING.value
                candidate_row.current_worker = worker_id
                candidate_row.processing_started_at = started_at
                _mark_stage(candidate_row, ArticleProcessingStage.FETCHING, started_at)
                candidate_row.updated_at = started_at
        return run

    async def heartbeat(
        self,
        *,
        candidate_id: UUID,
        worker_id: str,
        lease_version: int,
        lease_seconds: int,
    ) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            updated = await session.scalar(
                update(UrlCandidateModel)
                .where(
                    UrlCandidateModel.id == candidate_id,
                    UrlCandidateModel.lease_owner == worker_id,
                    UrlCandidateModel.lease_version == lease_version,
                    UrlCandidateModel.state == UrlCandidateState.LEASED.value,
                    UrlCandidateModel.lease_expires_at > now,
                )
                .values(
                    lease_heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
                .returning(UrlCandidateModel.id)
            )
            return updated is not None

    async def update_processing_stage(
        self,
        *,
        candidate: LeasedUrlCandidate,
        stage: ArticleProcessingStage,
        occurred_at: datetime,
        worker_id: str | None = None,
        run_id: UUID | None = None,
        content_type: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
        processing_duration_ms: int | None = None,
    ) -> None:
        del run_id
        async with self._session_factory() as session, session.begin():
            candidate_row = await session.get(UrlCandidateModel, candidate.id, with_for_update=True)
            if candidate_row is None:
                raise LookupError(f"url candidate not found: {candidate.id}")
            _assert_candidate_lease(candidate_row, candidate)
            candidate_row.processing_stage = stage.value
            if worker_id is not None:
                candidate_row.current_worker = worker_id
            if content_type is not None:
                candidate_row.content_type = content_type[:160]
            if failure_code is not None:
                candidate_row.last_failure_code = failure_code[:160]
            if failure_message is not None:
                candidate_row.last_failure_message = failure_message[:2_000]
            if processing_duration_ms is not None:
                candidate_row.processing_duration_ms = processing_duration_ms
            _mark_stage(candidate_row, stage, occurred_at)
            candidate_row.updated_at = occurred_at

    async def reject_before_fetch(
        self,
        *,
        candidate: LeasedUrlCandidate,
        worker_id: str,
        trace_id: UUID,
        rejected_at: datetime,
        reason: str,
        message: str,
    ) -> None:
        run_id = uuid7()
        async with self._session_factory() as session, session.begin():
            session.add(
                ArticleFetchRunModel(
                    id=run_id,
                    candidate_id=candidate.id,
                    worker_id=worker_id,
                    trace_id=trace_id,
                    status=ArticleFetchRunStatus.REJECTED.value,
                    started_at=rejected_at,
                    completed_at=rejected_at,
                    error_type=reason,
                    error_message=message,
                    fetch_job_id=candidate.fetch_job_id,
                    lease_version=candidate.lease_version,
                )
            )
            candidate_row = await session.get(UrlCandidateModel, candidate.id, with_for_update=True)
            if candidate_row is not None:
                _assert_candidate_lease(candidate_row, candidate)
                candidate_row.state = UrlCandidateState.REJECTED.value
                candidate_row.processing_stage = ArticleProcessingStage.REJECTED.value
                candidate_row.lease_owner = None
                candidate_row.lease_heartbeat_at = None
                candidate_row.lease_expires_at = None
                candidate_row.current_worker = None
                candidate_row.last_fetch_at = rejected_at
                candidate_row.last_error = f"{reason}: {message}"
                candidate_row.last_failure_code = reason[:160]
                candidate_row.last_failure_message = message[:2_000]
                candidate_row.processing_completed_at = rejected_at
                if candidate_row.processing_started_at is not None:
                    candidate_row.processing_duration_ms = _duration_ms(
                        candidate_row.processing_started_at,
                        rejected_at,
                    )
                _mark_stage(candidate_row, ArticleProcessingStage.REJECTED, rejected_at)
                candidate_row.updated_at = rejected_at

            await _add_outbox(
                session,
                IntegrationEvent(
                    event_type="article.fetch.rejected",
                    aggregate_type="url_candidate",
                    aggregate_id=candidate.id,
                    payload={
                        "candidate_id": str(candidate.id),
                        "fetch_run_id": str(run_id),
                        "attempt_count": candidate.attempt_count,
                        "reason": reason,
                        "message": message,
                        "url": candidate.normalized_url,
                        "published_at": (
                            candidate.published_at.isoformat()
                            if candidate.published_at
                            else None
                        ),
                        "first_discovered_at": (
                            candidate.first_discovered_at.isoformat()
                            if candidate.first_discovered_at
                            else None
                        ),
                    },
                    producer="article-processor",
                    correlation_id=trace_id,
                    idempotency_key=f"article.fetch.rejected:{run_id}",
                ),
            )

    async def complete_success(
        self,
        *,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        fetched: FetchResult,
        extracted: ExtractedArticle,
        raw_artifact: RawFetchArtifact | None,
        completed_at: datetime,
    ) -> ArticleProcessingResult:
        title = _fallback_title(extracted.title, fetched.final_url)
        canonical_url = extracted.canonical_url or fetched.final_url

        result: ArticleProcessingResult | None = None
        async with self._session_factory() as session, session.begin():
            candidate_row = await session.get(UrlCandidateModel, candidate.id, with_for_update=True)
            if candidate_row is None:
                raise LookupError(f"url candidate not found: {candidate.id}")
            _assert_candidate_lease(candidate_row, candidate)

            article = await session.scalar(
                select(ArticleModel).where(
                    ArticleModel.normalized_url_hash == candidate_row.url_fingerprint
                )
            )
            created_article = article is None
            created_event = False

            if article is None:
                decision, event, selected_candidate_features = await _decide_event(
                    session,
                    title=title,
                    text=extracted.text_content,
                    published_at=extracted.published_at,
                    observed_at=fetched.retrieved_at,
                )
                if event is None:
                    event = _new_provisional_event(
                        title=title,
                        text=extracted.text_content,
                        detected_at=fetched.retrieved_at,
                        candidate_id=candidate.id,
                    )
                    session.add(event)
                    await session.flush()
                    created_event = True
                    assignment_state = EventAssignmentState.PROVISIONAL
                    assignment_score = None
                    assignment_features = provisional_event_features(decision.candidates)
                else:
                    assignment_state = decision.state
                    assignment_score = decision.selected_score
                    assignment_features = selected_candidate_features
                    _update_existing_event_from_assignment(
                        event,
                        state=assignment_state,
                        observed_at=fetched.retrieved_at,
                        updated_at=completed_at,
                    )

                article = ArticleModel(
                    id=uuid7(),
                    publisher_id=candidate.publisher_id,
                    event_id=event.id,
                    canonical_url=canonical_url,
                    normalized_url_hash=candidate_row.url_fingerprint,
                    title=title,
                    language=extracted.language,
                    published_at=extracted.published_at,
                    first_observed_at=fetched.retrieved_at,
                    created_at=completed_at,
                    updated_at=completed_at,
                )
                session.add(article)
                await session.flush()
                session.add(
                    EventAssignmentModel(
                        id=uuid7(),
                        article_id=article.id,
                        event_id=event.id,
                        state=assignment_state.value,
                        score=assignment_score,
                        candidate_features=assignment_features,
                        policy_version=f"{MATCHING_POLICY_VERSION}:event-assignment-v1",
                        is_current=True,
                        assigned_at=completed_at,
                    )
                )
            else:
                article.canonical_url = canonical_url
                article.title = title
                article.language = extracted.language or article.language
                article.published_at = extracted.published_at or article.published_at
                article.updated_at = completed_at

            # Inspect the latest chronological revision, not any historical
            # version that happened to have the same body hash. This captures
            # headline-only changes and A -> B -> A body reversions.
            latest_version = await session.scalar(
                select(ArticleVersionModel)
                .where(ArticleVersionModel.article_id == article.id)
                .order_by(ArticleVersionModel.version_number.desc())
                .limit(1)
            )
            unchanged_revision = (
                latest_version is not None
                and latest_version.content_sha256 == extracted.content_sha256
                and latest_version.title == title
                and latest_version.byline == extracted.byline
                and latest_version.language == extracted.language
                and latest_version.published_at == extracted.published_at
                and latest_version.final_url == fetched.final_url
            )
            existing_version = latest_version if unchanged_revision else None
            created_version = not unchanged_revision
            version_id: UUID | None = existing_version.id if existing_version else None
            claim_count = 0
            claim_ids: list[UUID] = []

            if existing_version is None:
                version_number = (latest_version.version_number if latest_version else 0) + 1
                version = ArticleVersionModel(
                    id=uuid7(),
                    article_id=article.id,
                    version_number=version_number,
                    source_url=fetched.requested_url,
                    final_url=fetched.final_url,
                    title=title,
                    byline=extracted.byline,
                    language=extracted.language,
                    published_at=extracted.published_at,
                    retrieved_at=fetched.retrieved_at,
                    content_sha256=extracted.content_sha256,
                    text_content=extracted.text_content,
                    extraction_method=extracted.extraction_method,
                    extraction_warnings=list(extracted.warnings),
                    metadata_={
                        **extracted.metadata,
                        "digest_excerpt": prepare_excerpt(extracted.text_content, title,
                            (extracted.published_at or fetched.retrieved_at).year),
                        "content_lineage": fingerprint_metadata(
                            fingerprint_content(extracted.text_content)
                        ),
                        "fetch_run_id": str(run.id),
                        "body_sha256": fetched.body_sha256,
                        "raw_fetch_artifact": (
                            raw_artifact.to_metadata()
                            if raw_artifact
                            else None
                        ),
                        "redirect_chain": list(fetched.redirect_chain),
                    },
                    created_at=completed_at,
                )
                session.add(version)
                await session.flush()
                version_id = version.id
                claim_ids = _persist_claims_for_version(
                    session,
                    article=article,
                    version=version,
                    created_at=completed_at,
                )
                claim_count = len(claim_ids)
                await _persist_source_candidates(
                    session,
                    publisher_id=candidate.publisher_id,
                    external_links=extracted.metadata.get("external_links", []),
                    observed_at=completed_at,
                )

            await _upsert_article_identity(session, article=article, version=(version if existing_version is None else existing_version), observed_at=completed_at)

            await session.execute(
                update(ArticleFetchRunModel)
                .where(ArticleFetchRunModel.id == run.id)
                .values(
                    status=ArticleFetchRunStatus.SUCCEEDED.value,
                    completed_at=completed_at,
                    http_status=fetched.status_code,
                    response_bytes=len(fetched.body),
                    final_url=fetched.final_url,
                    body_sha256=fetched.body_sha256,
                )
            )
            candidate_row.state = UrlCandidateState.PROCESSED.value
            candidate_row.processing_stage = ArticleProcessingStage.COMPLETED.value
            candidate_row.article_id = article.id
            candidate_row.lease_owner = None
            candidate_row.lease_heartbeat_at = None
            candidate_row.lease_expires_at = None
            candidate_row.current_worker = None
            candidate_row.last_fetch_at = completed_at
            candidate_row.last_error = None
            candidate_row.last_failure_code = None
            candidate_row.last_failure_message = None
            candidate_row.processing_completed_at = completed_at
            if candidate_row.processing_started_at is not None:
                candidate_row.processing_duration_ms = _duration_ms(
                    candidate_row.processing_started_at,
                    completed_at,
                )
            _mark_stage(candidate_row, ArticleProcessingStage.PERSISTED, completed_at)
            _mark_stage(candidate_row, ArticleProcessingStage.COMPLETED, completed_at)
            candidate_row.updated_at = completed_at

            if created_event:
                await _add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="event.provisional_created",
                        aggregate_type="event",
                        aggregate_id=article.event_id,
                        payload={
                            "event_id": str(article.event_id),
                            "article_id": str(article.id),
                            "candidate_id": str(candidate.id),
                            "policy_version": MATCHING_POLICY_VERSION,
                            "assignment_features": assignment_features,
                        },
                        producer="article-processor",
                        correlation_id=run.trace_id,
                        idempotency_key=f"event.provisional_created:{article.event_id}",
                    ),
                )
            elif created_article:
                await _add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="event.article_linked",
                        aggregate_type="event",
                        aggregate_id=article.event_id,
                        payload={
                            "event_id": str(article.event_id),
                            "article_id": str(article.id),
                            "candidate_id": str(candidate.id),
                            "assignment_state": assignment_state.value,
                            "assignment_score": assignment_score,
                            "assignment_features": assignment_features,
                            "policy_version": MATCHING_POLICY_VERSION,
                        },
                        producer="article-processor",
                        correlation_id=run.trace_id,
                        idempotency_key=(
                            f"event.article_linked:{article.event_id}:{article.id}"
                        ),
                    ),
                )
            if created_article:
                await _add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="article.ingested",
                        aggregate_type="article",
                        aggregate_id=article.id,
                        payload={
                            "article_id": str(article.id),
                            "event_id": str(article.event_id),
                            "candidate_id": str(candidate.id),
                            "canonical_url": article.canonical_url,
                            "assignment_state": assignment_state.value,
                            "assignment_score": assignment_score,
                        },
                        producer="article-processor",
                        correlation_id=run.trace_id,
                        idempotency_key=f"article.ingested:{article.id}",
                    ),
                )
            if created_version and version_id is not None:
                await _add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="article.version_created",
                        aggregate_type="article",
                        aggregate_id=article.id,
                        payload={
                            "article_id": str(article.id),
                            "version_id": str(version_id),
                            "candidate_id": str(candidate.id),
                            "content_sha256": extracted.content_sha256,
                            "extraction_method": extracted.extraction_method,
                            "warnings": list(extracted.warnings),
                        },
                        producer="article-processor",
                        correlation_id=run.trace_id,
                        idempotency_key=f"article.version_created:{version_id}",
                    ),
                )
                # Historical enrichment is queued in the same transaction as the
                # immutable article version. The separate worker can fail/retry without
                # blocking article visibility or extraction throughput.
                await session.execute(
                    insert(ArticleHistoricalEnrichmentJobModel)
                    .values(
                        id=uuid7(),
                        article_id=article.id,
                        article_version_id=version_id,
                        event_id=article.event_id,
                        state="queued",
                        attempt_count=0,
                        refresh_count=0,
                        last_refresh_reason=None,
                        last_reconciled_at=None,
                        next_attempt_at=completed_at,
                        lease_owner=None,
                        lease_expires_at=None,
                        cutoff_at=version.retrieved_at,
                        query_terms=[],
                        last_error=None,
                        started_at=None,
                        completed_at=None,
                        created_at=completed_at,
                        updated_at=completed_at,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_historical_enrichment_job_version",
                    )
                )
                await _add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="article.historical_enrichment_queued",
                        aggregate_type="article",
                        aggregate_id=article.id,
                        payload={
                            "article_id": str(article.id),
                            "version_id": str(version_id),
                            "event_id": str(article.event_id),
                            "cutoff_at": version.retrieved_at.isoformat(),
                        },
                        producer="article-processor",
                        correlation_id=run.trace_id,
                        idempotency_key=f"article.historical_enrichment_queued:{version_id}",
                    ),
                )
                await _add_outbox(
                    session,
                    IntegrationEvent(
                        event_type="article.claims_extracted",
                        aggregate_type="article",
                        aggregate_id=article.id,
                        payload={
                            "article_id": str(article.id),
                            "version_id": str(version_id),
                            "claim_count": claim_count,
                            "claim_ids": [str(claim_id) for claim_id in claim_ids],
                            "extractor_version": CLAIM_EXTRACTOR_VERSION,
                            "verification_label": (
                                ClaimVerificationLabel.NOT_CHECKABLE.value
                            ),
                        },
                        producer="article-processor",
                        correlation_id=run.trace_id,
                        idempotency_key=f"article.claims_extracted:{version_id}",
                    ),
                )

            await session.flush()
            logger.info(
                "database_flush_succeeded",
                candidate_id=str(candidate.id),
                fetch_run_id=str(run.id),
                article_id=str(article.id),
                event_id=str(article.event_id),
                version_id=str(version_id) if version_id else None,
                created_article=created_article,
                created_event=created_event,
                created_version=created_version,
                claim_count=claim_count,
                correlation_id=str(run.trace_id),
            )

            result = ArticleProcessingResult(
                candidate_id=candidate.id,
                article_id=article.id,
                event_id=article.event_id,
                version_id=version_id,
                created_article=created_article,
                created_event=created_event,
                created_version=created_version,
                claim_count=claim_count,
            )

        if result is None:
            raise RuntimeError("article persistence completed without a result")
        logger.info(
            "database_commit_succeeded",
            candidate_id=str(candidate.id),
            fetch_run_id=str(run.id),
            article_id=str(result.article_id),
            event_id=str(result.event_id),
            version_id=str(result.version_id) if result.version_id else None,
            created_article=result.created_article,
            created_event=result.created_event,
            created_version=result.created_version,
            claim_count=result.claim_count,
            correlation_id=str(run.trace_id),
        )
        return result

    async def complete_failure(
        self,
        *,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        completed_at: datetime,
        error_type: str,
        error_message: str,
        retry_at: datetime | None,
        terminal: bool,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(ArticleFetchRunModel)
                .where(ArticleFetchRunModel.id == run.id)
                .values(
                    status=ArticleFetchRunStatus.FAILED.value,
                    completed_at=completed_at,
                    error_type=error_type,
                    error_message=error_message,
                )
            )
            candidate_row = await session.get(UrlCandidateModel, candidate.id, with_for_update=True)
            if candidate_row is not None:
                _assert_candidate_lease(candidate_row, candidate)
                failure_stage = (
                    ArticleProcessingStage.PERMANENT_FAILURE
                    if terminal
                    else ArticleProcessingStage.RETRYABLE_FAILURE
                )
                candidate_row.state = (
                    UrlCandidateState.FAILED.value
                    if terminal
                    else UrlCandidateState.RETRY.value
                )
                candidate_row.processing_stage = failure_stage.value
                candidate_row.next_fetch_at = retry_at or completed_at
                candidate_row.lease_owner = None
                candidate_row.lease_heartbeat_at = None
                candidate_row.lease_expires_at = None
                candidate_row.current_worker = None
                candidate_row.last_fetch_at = completed_at
                candidate_row.last_error = f"{error_type}: {error_message}"
                candidate_row.last_failure_code = error_type[:160]
                candidate_row.last_failure_message = error_message[:2_000]
                if terminal:
                    candidate_row.processing_completed_at = completed_at
                if candidate_row.processing_started_at is not None:
                    candidate_row.processing_duration_ms = _duration_ms(
                        candidate_row.processing_started_at,
                        completed_at,
                    )
                _mark_stage(candidate_row, failure_stage, completed_at)
                candidate_row.updated_at = completed_at

            await _add_outbox(
                session,
                IntegrationEvent(
                    event_type="article.fetch.failed",
                    aggregate_type="url_candidate",
                    aggregate_id=candidate.id,
                    payload={
                        "candidate_id": str(candidate.id),
                        "fetch_run_id": str(run.id),
                        "attempt_count": candidate.attempt_count,
                        "terminal": terminal,
                        "retry_at": retry_at.isoformat() if retry_at else None,
                        "error_type": error_type,
                    },
                    producer="article-processor",
                    correlation_id=run.trace_id,
                    idempotency_key=f"article.fetch.failed:{run.id}",
                ),
            )


def _assert_candidate_lease(row: UrlCandidateModel, candidate: LeasedUrlCandidate) -> None:
    if (
        row.lease_owner is None or row.lease_version != candidate.lease_version
        or (candidate.lease_owner is not None and row.lease_owner != candidate.lease_owner)
        or row.state != UrlCandidateState.LEASED.value
        or row.lease_expires_at is None or row.lease_expires_at <= datetime.now(UTC)
    ):
        raise RuntimeError("article lease lost before state mutation")


async def _upsert_article_identity(
    session: AsyncSession,
    *,
    article: ArticleModel,
    version: ArticleVersionModel,
    observed_at: datetime,
) -> None:
    existing_member = await session.scalar(
        select(ArticleIdentityMemberModel).where(ArticleIdentityMemberModel.article_id == article.id)
    )
    if existing_member is not None:
        return
    fingerprint = fingerprint_from_metadata((version.metadata_ or {}).get("content_lineage"))
    if fingerprint is None:
        fingerprint = fingerprint_content(version.text_content)

    identity: ArticleIdentityModel | None = None
    membership_basis = "unique_content"
    similarity: float | None = None

    # Compare only recent reports in the same event. This is deliberately conservative:
    # high similarity reduces independence but never establishes factual agreement.
    candidate_versions = (
        await session.execute(
            select(ArticleVersionModel, ArticleModel)
            .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
            .where(
                ArticleModel.event_id == article.event_id,
                ArticleModel.id != article.id,
            )
            .order_by(ArticleVersionModel.retrieved_at.desc())
            .limit(250)
        )
    ).all()
    best_article: ArticleModel | None = None
    best_similarity = 0.0
    for other_version, other_article in candidate_versions:
        other_fp = fingerprint_from_metadata((other_version.metadata_ or {}).get("content_lineage"))
        if other_fp is None:
            continue
        score = estimate_lineage_similarity(fingerprint, other_fp)
        if score > best_similarity:
            best_similarity = score
            best_article = other_article
    if best_article is not None and best_similarity >= 0.85:
        other_member = await session.scalar(
            select(ArticleIdentityMemberModel).where(ArticleIdentityMemberModel.article_id == best_article.id)
        )
        if other_member is not None:
            identity = await session.get(ArticleIdentityModel, other_member.identity_id)
        membership_basis = "exact_content" if best_similarity >= 0.999 else "near_duplicate"
        similarity = best_similarity

    if identity is None:
        identity = await session.scalar(
            select(ArticleIdentityModel).where(ArticleIdentityModel.identity_key == fingerprint.exact_signature)
        )
    if identity is None:
        identity = ArticleIdentityModel(
            id=uuid7(),
            identity_key=fingerprint.exact_signature,
            representative_article_id=article.id,
            first_observed_at=observed_at,
            last_observed_at=observed_at,
            member_count=0,
            metadata_={"lineage_version": fingerprint.version},
            created_at=observed_at,
            updated_at=observed_at,
        )
        session.add(identity)
        await session.flush()
    identity.member_count = int(identity.member_count or 0) + 1
    identity.last_observed_at = max(identity.last_observed_at, observed_at)
    identity.updated_at = observed_at
    session.add(
        ArticleIdentityMemberModel(
            id=uuid7(),
            identity_id=identity.id,
            article_id=article.id,
            publisher_id=article.publisher_id,
            membership_basis=membership_basis,
            content_sha256=version.content_sha256,
            similarity=similarity,
            created_at=observed_at,
        )
    )


def _fallback_title(extracted_title: str | None, final_url: str) -> str:
    if extracted_title:
        return extracted_title[:1_000]
    return final_url[:1_000]


def _persist_claims_for_version(
    session: AsyncSession,
    *,
    article: ArticleModel,
    version: ArticleVersionModel,
    created_at: datetime,
) -> list[UUID]:
    claim_ids: list[UUID] = []
    for claim in extract_claims(version.text_content):
        claim_id = uuid7()
        provenance = locate_pdf_source_sentence(
            version.text_content,
            version.metadata_.get("document_pages"),
            claim.source_sentence,
            expected_source_url=version.final_url,
        )
        features = dict(claim.features)
        if provenance is not None:
            features["document_provenance"] = provenance
        session.add(
            ArticleClaimModel(
                id=claim_id,
                article_id=article.id,
                article_version_id=version.id,
                claim_text=claim.text,
                claim_sha256=claim.claim_sha256,
                sentence_index=claim.sentence_index,
                extractor_version=CLAIM_EXTRACTOR_VERSION,
                extraction_features=features,
                created_at=created_at,
            )
        )
        session.add(
            ClaimEvidenceLinkModel(
                id=uuid7(),
                claim_id=claim_id,
                evidence_article_id=article.id,
                evidence_article_version_id=version.id,
                source_url=version.final_url,
                source_type="originating_article",
                relationship="origin",
                retrieved_at=version.retrieved_at,
                similarity_score=1.0,
                independence_score=0.0,
                metadata_={
                    "source_independence_reason": (
                        "The originating article is evidence for claim extraction, "
                        "not independent confirmation."
                    ),
                    "article_id": str(article.id),
                    "article_version_id": str(version.id),
                    "evidence_passage": claim.text,
                    "evidence_passage_sha256": claim.claim_sha256,
                    "sentence_index": claim.sentence_index,
                    "clause_index": claim.clause_index,
                    "source_sentence": claim.source_sentence,
                    **({"document_provenance": provenance} if provenance else {}),
                    "claim_type": claim.features.get("claim_type"),
                    "claim_family_key": claim.features.get("claim_family_key"),
                },
                created_at=created_at,
            )
        )
        session.add(
            ClaimVerificationModel(
                id=uuid7(),
                claim_id=claim_id,
                label=ClaimVerificationLabel.NOT_CHECKABLE.value,
                confidence_score=None,
                methodology_version="verification-bootstrap-v1",
                confidence_factors={
                    "source_reliability": None,
                    "independent_confirmation_count": 0,
                    "evidence_consistency": None,
                    "recency": None,
                    "contradictory_evidence_weight": 0,
                    "claim_type": claim.features.get("claim_type"),
                    "checkability_score": claim.features.get("checkability_score"),
                    "expected_primary_evidence": claim.features.get(
                        "expected_primary_evidence"
                    ),
                },
                reasoning_trace={
                    "conclusion": "Insufficient independent evidence available.",
                    "reason": (
                        "Only the originating article has been stored as evidence. "
                        "No independent retrieval or contradiction analysis has run yet."
                    ),
                    "origin_evidence_linked": True,
                    "independent_evidence_required_for_supported_labels": True,
                },
                created_at=created_at,
            )
        )
        claim_ids.append(claim_id)
    return claim_ids


async def _decide_event(
    session: AsyncSession,
    *,
    title: str,
    text: str,
    published_at: datetime | None,
    observed_at: datetime,
) -> tuple[EventAssignmentDecision, EventModel | None, dict[str, float]]:
    references = await _load_recent_event_references(
        session,
        observed_at=published_at or observed_at,
    )
    incoming = ArticleEventProfile(
        title=title,
        text=text,
        published_at=published_at,
        observed_at=observed_at,
    )
    candidates = build_event_candidates(incoming, references)
    decision = decide_event_assignment(candidates)
    if decision.selected_event_id is None:
        return decision, None, {}

    selected_candidate = next(
        candidate
        for candidate in decision.candidates
        if candidate.event_id == decision.selected_event_id
    )
    event = await session.get(EventModel, decision.selected_event_id)
    return decision, event, event_candidate_features(selected_candidate)


async def _load_recent_event_references(
    session: AsyncSession,
    *,
    observed_at: datetime,
    lookback_days: int = 45,
    max_rows: int = 500,
) -> tuple[EventReference, ...]:
    window_start = observed_at - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            select(EventModel, ArticleModel, ArticleVersionModel)
            .join(ArticleModel, ArticleModel.event_id == EventModel.id)
            .join(ArticleVersionModel, ArticleVersionModel.article_id == ArticleModel.id)
            .where(
                EventModel.lifecycle_status == "active",
                EventModel.last_material_change_at >= window_start,
            )
            .order_by(desc(ArticleVersionModel.created_at))
            .limit(max_rows)
        )
    ).all()

    grouped: dict[UUID, dict[str, object]] = {}
    for event, article, version in rows:
        item = grouped.setdefault(
            event.id,
            {
                "title": event.title,
                "first_detected_at": event.first_detected_at,
                "latest_observed_at": article.first_observed_at,
                "texts": [],
            },
        )
        latest_observed_at = item["latest_observed_at"]
        if isinstance(latest_observed_at, datetime):
            item["latest_observed_at"] = max(latest_observed_at, article.first_observed_at)
        texts = item["texts"]
        if isinstance(texts, list) and len(texts) < 3:
            texts.append(f"{article.title}\n{version.text_content[:1_500]}")

    references: list[EventReference] = []
    for event_id, item in grouped.items():
        title = item["title"]
        first_detected_at = item["first_detected_at"]
        latest_observed_at = item["latest_observed_at"]
        texts = item["texts"]
        if not isinstance(title, str) or not isinstance(first_detected_at, datetime):
            continue
        references.append(
            EventReference(
                event_id=event_id,
                title=title,
                text="\n".join(texts) if isinstance(texts, list) else "",
                first_detected_at=first_detected_at,
                latest_observed_at=(
                    latest_observed_at
                    if isinstance(latest_observed_at, datetime)
                    else None
                ),
            )
        )
    return tuple(references)


def _update_existing_event_from_assignment(
    event: EventModel,
    *,
    state: EventAssignmentState,
    observed_at: datetime,
    updated_at: datetime,
) -> None:
    event.last_material_change_at = max(event.last_material_change_at, observed_at)
    event.updated_at = updated_at
    event.assignment_status = _stronger_assignment_status(event.assignment_status, state)


def _stronger_assignment_status(
    existing: str,
    incoming: EventAssignmentState,
) -> str:
    ranking = {
        EventAssignmentState.PROVISIONAL.value: 0,
        EventAssignmentState.CANDIDATE.value: 1,
        EventAssignmentState.CONFIRMED.value: 2,
    }
    existing_rank = ranking.get(existing, 0)
    incoming_rank = ranking[incoming.value]
    return incoming.value if incoming_rank > existing_rank else existing


def _new_provisional_event(
    *,
    title: str,
    text: str,
    detected_at: datetime,
    candidate_id: UUID,
) -> EventModel:
    event_id = uuid7()
    return EventModel(
        id=event_id,
        slug=f"event-{event_id.hex}",
        title=title,
        lifecycle_status="active",
        assignment_status=EventAssignmentState.PROVISIONAL.value,
        first_detected_at=detected_at,
        last_material_change_at=detected_at,
        metadata_={
            "created_from_candidate_id": str(candidate_id),
            "event_creation_policy": MATCHING_POLICY_VERSION,
            "top_terms": list(top_terms(f"{title}\n{text}")),
        },
        created_at=detected_at,
        updated_at=detected_at,
    )


def _mark_stage(
    candidate_row: UrlCandidateModel,
    stage: ArticleProcessingStage,
    occurred_at: datetime,
) -> None:
    timestamps = dict(candidate_row.stage_timestamps or {})
    timestamps[stage.value] = occurred_at.isoformat()
    candidate_row.stage_timestamps = timestamps


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, round((completed_at - started_at).total_seconds() * 1_000))


async def _persist_source_candidates(
    session: AsyncSession,
    *,
    publisher_id: UUID,
    external_links: object,
    observed_at: datetime,
) -> None:
    if not isinstance(external_links, list):
        return
    origins: set[tuple[str, str]] = set()
    for raw in external_links:
        if not isinstance(raw, str):
            continue
        parsed = urlsplit(raw)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        origins.add((origin, host))
    for candidate_url, candidate_domain in sorted(origins):
        statement = insert(SourceCandidateModel).values(
            id=uuid7(),
            discovered_from_publisher_id=publisher_id,
            candidate_url=candidate_url,
            candidate_domain=candidate_domain,
            evidence_type="article_outbound_link",
            evidence_count=1,
            score=0.25,
            state="quarantined",
            first_seen_at=observed_at,
            last_seen_at=observed_at,
            metadata_={"activation_policy": "manual_or_validated_probe_required"},
        )
        statement = statement.on_conflict_do_update(
            constraint="uq_source_candidates_url",
            set_={
                "evidence_count": SourceCandidateModel.evidence_count + 1,
                "score": func.least(0.9, SourceCandidateModel.score + 0.08),
                "last_seen_at": observed_at,
            },
        )
        await session.execute(statement)


async def _add_outbox(session: AsyncSession, event: IntegrationEvent) -> None:
    await session.execute(
        insert(OutboxEventModel)
        .values(
            id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
            producer=event.producer,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            traceparent=event.traceparent,
            idempotency_key=event.idempotency_key,
        )
        .on_conflict_do_nothing(
            constraint="uq_outbox_events_idempotency_key",
        )
    )
