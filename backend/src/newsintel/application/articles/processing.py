import asyncio
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.adapters.artifacts.local_store import RawFetchArtifact
from newsintel.adapters.extractors.article_html import ExtractedArticle, ExtractionProfile
from newsintel.adapters.extractors.document_pdf import extract_pdf_document
from newsintel.adapters.http.crawl_policy import RobotsDeniedError
from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult
from newsintel.adapters.rendering.browser_client import RenderedPage
from newsintel.core.ids import uuid7
from newsintel.domain.acquisition.article_filter import (
    DEFAULT_RECENT_WINDOW_HOURS,
    should_admit_article_url,
)
from newsintel.domain.intelligence.extraction_fidelity import assess_extraction_fidelity

logger = structlog.get_logger(__name__)


class UrlCandidateState(StrEnum):
    PAUSED = "paused"
    READY = "ready"
    LEASED = "leased"
    RETRY = "retry"
    PROCESSED = "processed"
    FAILED = "failed"
    REJECTED = "rejected"


class ArticleProcessingStage(StrEnum):
    PAUSED = "paused"
    DISCOVERED = "discovered"
    ADMITTED = "admitted"
    QUEUED = "queued"
    LEASED = "leased"
    FETCHING = "fetching"
    FETCHED = "fetched"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    PARTIAL = "partial"
    VALIDATED = "validated"
    PERSISTING = "persisting"
    PERSISTED = "persisted"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    REJECTED = "rejected"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"


class ArticleFetchRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class ArticleProcessingError(RuntimeError):
    pass


class NonRetryableArticleProcessingError(ArticleProcessingError):
    pass


class InsufficientArticleContentError(ArticleProcessingError):
    pass


class ArticleJobRejectedError(ArticleProcessingError):
    pass


class ArticleAccessBlockedError(NonRetryableArticleProcessingError):
    pass


class ExtractionQualityError(NonRetryableArticleProcessingError):
    pass


class ArticleNotFoundError(NonRetryableArticleProcessingError):
    pass


_NON_RETRYABLE_HTTP_STATUSES = {401, 402, 403, 451}
_PERMANENT_HTTP_STATUSES = {400, 404, 410}
_FATAL_EXTRACTION_WARNINGS = {
    "missing_text_content",
}
_PARTIAL_EXTRACTION_WARNINGS = {
    "short_text_content",
    "low_extraction_quality",
    "possible_paywall_or_partial_content",
    "possible_subscription_boilerplate",
}


@dataclass(frozen=True, slots=True)
class LeasedUrlCandidate:
    id: UUID
    publisher_id: UUID
    normalized_url: str
    attempt_count: int
    published_at: datetime | None = None
    first_discovered_at: datetime | None = None
    url_type: str | None = None
    lease_version: int = 0
    fetch_job_id: UUID | None = None
    lease_owner: str | None = None


@dataclass(frozen=True, slots=True)
class ArticleFetchRun:
    id: UUID
    candidate_id: UUID
    worker_id: str
    trace_id: UUID
    started_at: datetime
    lease_version: int = 0
    fetch_job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ArticleProcessingResult:
    candidate_id: UUID
    article_id: UUID
    event_id: UUID
    version_id: UUID | None
    created_article: bool
    created_event: bool
    created_version: bool
    claim_count: int = 0


class ArticleProcessingRepository(Protocol):
    async def lease_due_candidates(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> Sequence[LeasedUrlCandidate]: ...

    async def start_fetch(
        self,
        *,
        candidate_id: UUID,
        worker_id: str,
        trace_id: UUID,
        started_at: datetime,
        lease_version: int = 0,
    ) -> ArticleFetchRun: ...

    async def heartbeat(
        self, *, candidate_id: UUID, worker_id: str, lease_version: int, lease_seconds: int
    ) -> bool: ...

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
    ) -> None: ...

    async def complete_success(
        self,
        *,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        fetched: FetchResult,
        extracted: ExtractedArticle,
        raw_artifact: RawFetchArtifact | None,
        completed_at: datetime,
    ) -> ArticleProcessingResult: ...

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
    ) -> None: ...

    async def reject_before_fetch(
        self,
        *,
        candidate: LeasedUrlCandidate,
        worker_id: str,
        trace_id: UUID,
        rejected_at: datetime,
        reason: str,
        message: str,
    ) -> None: ...


class Fetcher(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...


class RawArtifactStore(Protocol):
    async def save_raw_pdf(
        self, *, candidate_id: UUID, body: bytes, body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact: ...

    async def save_raw_html(
        self,
        *,
        candidate_id: UUID,
        body: bytes,
        body_sha256: str,
        retrieved_at: datetime,
    ) -> RawFetchArtifact: ...


class ArticleExtractor(Protocol):
    def __call__(
        self,
        html: bytes,
        *,
        base_url: str,
        profile: ExtractionProfile | None = None,
    ) -> ExtractedArticle: ...


class BrowserRenderer(Protocol):
    async def render(
        self,
        *,
        url: str,
        allowed_domains: tuple[str, ...],
    ) -> RenderedPage: ...


class ExtractionProfileStore(Protocol):
    async def resolve(self, publisher_id: UUID) -> ExtractionProfile | None: ...

    async def record_success(
        self,
        *,
        publisher_id: UUID,
        extracted: ExtractedArticle,
    ) -> None: ...

    async def record_failure(self, *, publisher_id: UUID) -> None: ...


def retry_at_for_attempt(
    attempt_count: int,
    *,
    base_seconds: int,
    max_seconds: int,
    jitter_ratio: float = 0.0,
    now: datetime | None = None,
) -> datetime:
    if attempt_count < 1:
        raise ValueError("attempt_count must be positive")
    current_time = now or datetime.now(UTC)
    delay = min(max_seconds, base_seconds * (2 ** min(attempt_count - 1, 10)))
    if jitter_ratio > 0:
        jitter = delay * min(max(jitter_ratio, 0.0), 1.0)
        delay = max(1.0, delay + random.uniform(-jitter, jitter))  # noqa: S311
    return current_time + timedelta(seconds=delay)


class ArticleProcessor:
    def __init__(
        self,
        *,
        repository: ArticleProcessingRepository,
        fetcher: Fetcher,
        extractor: ArticleExtractor,
        raw_artifact_store: RawArtifactStore | None = None,
        extraction_profiles: ExtractionProfileStore | None = None,
        browser_renderer: BrowserRenderer | None = None,
        browser_renderer_min_word_count: int = 80,
        browser_renderer_min_quality_score: float = 0.45,
        max_attempts: int = 3,
        retry_base_seconds: int = 120,
        retry_max_seconds: int = 3_600,
        retry_jitter_ratio: float = 0.15,
        recent_article_window_hours: int = DEFAULT_RECENT_WINDOW_HOURS,
        pdf_max_pages: int = 40,
        pdf_max_bytes: int = 8_000_000,
        pdf_ocr_enabled: bool = False,
        pdf_ocr_language: str = "eng",
        pdf_max_ocr_pages: int = 6,
        pdf_processing_timeout_seconds: int = 75,
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher
        self._extractor = extractor
        self._raw_artifact_store = raw_artifact_store
        self._extraction_profiles = extraction_profiles
        self._browser_renderer = browser_renderer
        self._browser_renderer_min_word_count = browser_renderer_min_word_count
        self._browser_renderer_min_quality_score = browser_renderer_min_quality_score
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._retry_max_seconds = retry_max_seconds
        self._retry_jitter_ratio = retry_jitter_ratio
        self._recent_article_window_hours = recent_article_window_hours
        self._pdf_max_pages = pdf_max_pages
        self._pdf_max_bytes = pdf_max_bytes
        self._pdf_ocr_enabled = pdf_ocr_enabled
        self._pdf_ocr_language = pdf_ocr_language
        self._pdf_max_ocr_pages = pdf_max_ocr_pages
        self._pdf_processing_timeout_seconds = pdf_processing_timeout_seconds

    async def process(
        self,
        candidate: LeasedUrlCandidate,
        *,
        worker_id: str,
    ) -> ArticleProcessingResult:
        started_at = datetime.now(UTC)
        trace_id = uuid7()
        context = _candidate_log_context(
            candidate,
            worker_id=worker_id,
            correlation_id=trace_id,
            started_at=started_at,
        )
        logger.info(
            "article_job_claimed",
            **context,
        )
        rejection = should_admit_article_url(
            candidate.normalized_url,
            published_at=candidate.published_at,
            observed_at=started_at,
            recent_window_hours=self._recent_article_window_hours,
            require_publication_date=False,
        )
        if not rejection.accepted:
            reason = rejection.reason.value if rejection.reason else "prefetch_rejected"
            message = f"queued URL rejected before HTTP fetch: {reason}"
            await self._repository.reject_before_fetch(
                candidate=candidate,
                worker_id=worker_id,
                trace_id=trace_id,
                rejected_at=started_at,
                reason=reason,
                message=message,
            )
            logger.info(
                "old_job_rejected",
                **context,
                reason=reason,
                classified_url_type=rejection.url_type.value,
                url_type_confidence=rejection.confidence,
                recent_article_window_hours=self._recent_article_window_hours,
            )
            raise ArticleJobRejectedError(message)

        run = await self._repository.start_fetch(
            candidate_id=candidate.id,
            worker_id=worker_id,
            trace_id=trace_id,
            started_at=started_at,
            lease_version=candidate.lease_version,
        )
        context = {**context, "fetch_run_id": str(run.id)}
        try:
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.FETCHING,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info("page_fetch_started", **context)
            try:
                fetched = await self._fetcher.fetch(FetchRequest(url=candidate.normalized_url))
            except RobotsDeniedError as exc:
                # PermissionError inherits OSError. Letting it escape as such
                # makes the worker back off every publisher as a database outage.
                raise ArticleAccessBlockedError(str(exc)) from exc
            content_type = fetched.headers.get("content-type")
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.FETCHED,
                occurred_at=fetched.retrieved_at,
                worker_id=worker_id,
                run_id=run.id,
                content_type=content_type,
            )
            logger.info(
                "page_fetched",
                **context,
                final_url=fetched.final_url,
                http_status=fetched.status_code,
                content_type=content_type,
                response_bytes=len(fetched.body),
                body_sha256=fetched.body_sha256,
                redirect_chain=list(fetched.redirect_chain),
            )
            if fetched.status_code < 200 or fetched.status_code >= 300:
                if fetched.status_code in _NON_RETRYABLE_HTTP_STATUSES:
                    raise ArticleAccessBlockedError(
                        f"article access blocked HTTP {fetched.status_code}"
                    )
                if fetched.status_code in _PERMANENT_HTTP_STATUSES:
                    raise ArticleNotFoundError(
                        f"article returned permanent HTTP {fetched.status_code}"
                    )
                raise ArticleProcessingError(
                    f"article returned HTTP {fetched.status_code}"
                )
            is_pdf = (
                fetched.body.startswith(b"%PDF-")
                or "application/pdf" in (content_type or "").casefold()
                or urlsplit(fetched.final_url).path.casefold().endswith(".pdf")
            )
            raw_artifact = None
            if self._raw_artifact_store is not None:
                save_snapshot = (
                    self._raw_artifact_store.save_raw_pdf
                    if is_pdf else self._raw_artifact_store.save_raw_html
                )
                raw_artifact = await save_snapshot(
                    candidate_id=candidate.id,
                    body=fetched.body,
                    body_sha256=fetched.body_sha256,
                    retrieved_at=fetched.retrieved_at,
                )
                logger.info(
                    "raw_snapshot_saved",
                    **context,
                    raw_artifact_uri=raw_artifact.artifact_uri,
                    raw_artifact_sha256=raw_artifact.sha256,
                    raw_artifact_bytes=raw_artifact.byte_size,
                )
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.EXTRACTING,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info("extraction_started", **context, final_url=fetched.final_url)
            extraction_profile = (
                None if is_pdf else await self._resolve_extraction_profile(
                    publisher_id=candidate.publisher_id
                )
            )
            if is_pdf:
                extracted = await asyncio.to_thread(
                    extract_pdf_document,
                    fetched.body,
                    base_url=fetched.final_url,
                    max_pages=self._pdf_max_pages,
                    max_bytes=self._pdf_max_bytes,
                    ocr_enabled=self._pdf_ocr_enabled,
                    ocr_language=self._pdf_ocr_language,
                    max_ocr_pages=self._pdf_max_ocr_pages,
                    max_duration_seconds=self._pdf_processing_timeout_seconds,
                )
                if candidate.published_at is not None:
                    extracted = replace(
                        extracted,
                        published_at=candidate.published_at,
                        metadata={
                            **extracted.metadata,
                            "publication_date_basis": "discovery_candidate",
                        },
                    )
            else:
                extracted = (
                    self._extractor(
                        fetched.body,
                        base_url=fetched.final_url,
                        profile=extraction_profile,
                    )
                    if extraction_profile is not None
                    else self._extractor(fetched.body, base_url=fetched.final_url)
                )
            fidelity_html = fetched.body
            fidelity_base_url = fetched.final_url
            rendered_artifact = None
            rendered = (
                None if is_pdf else await self._maybe_render_browser(
                    fetched=fetched,
                    extracted=extracted,
                    profile=extraction_profile,
                    context=context,
                )
            )
            if rendered is not None:
                rendered_page, rendered_extracted = rendered
                if self._raw_artifact_store is not None:
                    rendered_artifact = await self._raw_artifact_store.save_raw_html(
                        candidate_id=candidate.id,
                        body=rendered_page.html,
                        body_sha256=rendered_page.html_sha256,
                        retrieved_at=datetime.now(UTC),
                    )
                extracted = replace(
                    rendered_extracted,
                    metadata={
                        **rendered_extracted.metadata,
                        "browser_rendered": True,
                        "browser_final_url": rendered_page.final_url,
                        "browser_rendered_html_sha256": rendered_page.html_sha256,
                        "browser_blocked_request_count": rendered_page.blocked_request_count,
                        "browser_allowed_request_count": rendered_page.allowed_request_count,
                        "browser_render_artifact": (
                            rendered_artifact.to_metadata() if rendered_artifact else None
                        ),
                    },
                )
                fidelity_html = rendered_page.html
                fidelity_base_url = rendered_page.final_url
            if not is_pdf:
                try:
                    fidelity = assess_extraction_fidelity(
                        fidelity_html,
                        base_url=fidelity_base_url,
                        article=extracted,
                    )
                    extracted = replace(
                        extracted,
                        metadata={
                            **extracted.metadata,
                            "extraction_fidelity": fidelity.to_dict(),
                        },
                    )
                except Exception as exc:
                    # Fidelity is an audit signal. A diagnostic failure must never
                    # make a successfully extracted public article disappear.
                    logger.warning(
                        "extraction_fidelity_assessment_failed",
                        **context,
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:300],
                    )
            if not extracted.text_content:
                if not is_pdf:
                    await self._record_extraction_profile_failure(
                        publisher_id=candidate.publisher_id
                    )
                raise InsufficientArticleContentError("article text could not be extracted")
            try:
                _raise_for_unacceptable_extraction(extracted)
            except Exception:
                if not is_pdf:
                    await self._record_extraction_profile_failure(
                        publisher_id=candidate.publisher_id
                    )
                raise
            if not is_pdf:
                await self._record_extraction_profile_success(
                    publisher_id=candidate.publisher_id,
                    extracted=extracted,
                )
            extraction_stage = (
                ArticleProcessingStage.PARTIAL
                if set(extracted.warnings) & _PARTIAL_EXTRACTION_WARNINGS
                else ArticleProcessingStage.EXTRACTED
            )
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=extraction_stage,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info(
                "extraction_succeeded",
                **context,
                final_url=fetched.final_url,
                status_code=fetched.status_code,
                canonical_url=extracted.canonical_url,
                content_sha256=extracted.content_sha256,
                extraction_method=extracted.extraction_method,
                warnings=list(extracted.warnings),
                partial=extraction_stage == ArticleProcessingStage.PARTIAL,
                word_count=extracted.word_count,
                extraction_quality_score=extracted.metadata.get(
                    "extraction_quality_score"
                ),
                extraction_fidelity_label=(
                    (extracted.metadata.get("extraction_fidelity") or {}).get("label")
                    if isinstance(extracted.metadata.get("extraction_fidelity"), dict)
                    else None
                ),
                extraction_fidelity_score=(
                    (extracted.metadata.get("extraction_fidelity") or {}).get("score")
                    if isinstance(extracted.metadata.get("extraction_fidelity"), dict)
                    else None
                ),
            )
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.VALIDATED,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info(
                "article_validation_succeeded",
                **context,
                canonical_url=extracted.canonical_url or fetched.final_url,
                content_sha256=extracted.content_sha256,
                word_count=extracted.word_count,
            )
        except Exception as exc:
            event_name = (
                "extraction_rejected"
                if isinstance(exc, NonRetryableArticleProcessingError)
                else "extraction_failed"
            )
            logger.exception(
                event_name,
                **context,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                failure_class=_failure_class(exc),
                failure_reason=_failure_code(exc),
            )
            await self._record_failure(candidate, run, exc)
            raise

        try:
            await self._repository.update_processing_stage(
                candidate=candidate,
                stage=ArticleProcessingStage.PERSISTING,
                occurred_at=datetime.now(UTC),
                worker_id=worker_id,
                run_id=run.id,
            )
            logger.info(
                "article_insert_started",
                **context,
                canonical_url=extracted.canonical_url or fetched.final_url,
                content_sha256=extracted.content_sha256,
            )
            result = await self._repository.complete_success(
                candidate=candidate,
                run=run,
                fetched=fetched,
                extracted=extracted,
                raw_artifact=raw_artifact,
                completed_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception(
                "database_commit_failed",
                **context,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                failure_class=_failure_class(exc),
                failure_reason=_failure_code(exc),
            )
            await self._record_failure(candidate, run, exc)
            raise

        logger.info(
            "article_saved",
            **context,
            article_id=str(result.article_id),
            event_id=str(result.event_id),
            version_id=str(result.version_id) if result.version_id else None,
            created_article=result.created_article,
            created_event=result.created_event,
            created_version=result.created_version,
        )
        if result.version_id:
            logger.info(
                "article_version_saved",
                **context,
                article_id=str(result.article_id),
                version_id=str(result.version_id),
                created_version=result.created_version,
            )
        logger.info(
            "claims_saved",
            **context,
            article_id=str(result.article_id),
            version_id=str(result.version_id) if result.version_id else None,
            claim_count=result.claim_count,
        )
        logger.info(
            "evidence_saved",
            **context,
            article_id=str(result.article_id),
            version_id=str(result.version_id) if result.version_id else None,
            evidence_count=result.claim_count,
        )
        logger.info(
            "article_job_completed",
            **context,
            article_id=str(result.article_id),
            event_id=str(result.event_id),
            version_id=str(result.version_id) if result.version_id else None,
            processing_duration_ms=_duration_ms(started_at, datetime.now(UTC)),
        )
        return result

    async def _maybe_render_browser(
        self,
        *,
        fetched: FetchResult,
        extracted: ExtractedArticle,
        profile: ExtractionProfile | None,
        context: dict[str, object],
    ) -> tuple[RenderedPage, ExtractedArticle] | None:
        if (
            self._browser_renderer is None
            or profile is None
            or not profile.browser_render_enabled
            or not _needs_browser_render(
                extracted,
                min_word_count=self._browser_renderer_min_word_count,
                min_quality=self._browser_renderer_min_quality_score,
            )
        ):
            return None
        host = urlsplit(fetched.final_url).hostname
        if not host:
            return None
        allowed_domains = _unique_domains((host, *profile.browser_allowed_domains))
        logger.info(
            "browser_render_started",
            **context,
            final_url=fetched.final_url,
            allowed_domains=list(allowed_domains),
            original_word_count=extracted.word_count,
            original_quality_score=extracted.metadata.get("extraction_quality_score"),
        )
        try:
            rendered_page = await self._browser_renderer.render(
                url=fetched.final_url,
                allowed_domains=allowed_domains,
            )
            rendered_extracted = self._extractor(
                rendered_page.html,
                base_url=rendered_page.final_url,
                profile=profile,
            )
        except Exception as exc:
            logger.warning(
                "browser_render_failed",
                **context,
                final_url=fetched.final_url,
                error_type=type(exc).__name__,
                error_message=str(exc)[:300],
            )
            return None
        if not _browser_candidate_better(rendered_extracted, extracted):
            logger.info(
                "browser_render_not_better",
                **context,
                original_word_count=extracted.word_count,
                rendered_word_count=rendered_extracted.word_count,
            )
            return None
        logger.info(
            "browser_render_succeeded",
            **context,
            final_url=rendered_page.final_url,
            rendered_word_count=rendered_extracted.word_count,
            extraction_method=rendered_extracted.extraction_method,
            blocked_request_count=rendered_page.blocked_request_count,
            allowed_request_count=rendered_page.allowed_request_count,
        )
        return rendered_page, rendered_extracted

    async def _resolve_extraction_profile(
        self,
        *,
        publisher_id: UUID,
    ) -> ExtractionProfile | None:
        if self._extraction_profiles is None:
            return None
        try:
            return await self._extraction_profiles.resolve(publisher_id)
        except Exception as exc:
            logger.warning(
                "extraction_profile_resolve_failed",
                publisher_id=str(publisher_id),
                error_type=type(exc).__name__,
                error_message=str(exc)[:300],
            )
            return None

    async def _record_extraction_profile_success(
        self,
        *,
        publisher_id: UUID,
        extracted: ExtractedArticle,
    ) -> None:
        if self._extraction_profiles is None:
            return
        try:
            await self._extraction_profiles.record_success(
                publisher_id=publisher_id,
                extracted=extracted,
            )
        except Exception as exc:
            logger.warning(
                "extraction_profile_learning_failed",
                publisher_id=str(publisher_id),
                error_type=type(exc).__name__,
                error_message=str(exc)[:300],
            )

    async def _record_extraction_profile_failure(
        self,
        *,
        publisher_id: UUID,
    ) -> None:
        if self._extraction_profiles is None:
            return
        try:
            await self._extraction_profiles.record_failure(publisher_id=publisher_id)
        except Exception as exc:
            logger.warning(
                "extraction_profile_failure_record_failed",
                publisher_id=str(publisher_id),
                error_type=type(exc).__name__,
                error_message=str(exc)[:300],
            )

    async def _record_failure(
        self,
        candidate: LeasedUrlCandidate,
        run: ArticleFetchRun,
        exc: Exception,
    ) -> None:
        now = datetime.now(UTC)
        terminal = candidate.attempt_count >= self._max_attempts or isinstance(
            exc,
            NonRetryableArticleProcessingError,
        )
        retry_at = (
            None
            if terminal
            else retry_at_for_attempt(
                candidate.attempt_count,
                base_seconds=self._retry_base_seconds,
                max_seconds=self._retry_max_seconds,
                jitter_ratio=self._retry_jitter_ratio,
                now=now,
            )
        )
        await self._repository.complete_failure(
            candidate=candidate,
            run=run,
            completed_at=now,
            error_type=type(exc).__name__,
            error_message=str(exc)[:2_000],
            retry_at=retry_at,
            terminal=terminal,
        )
        event_name = "article_job_dead_lettered" if terminal else "article_job_retry_scheduled"
        logger.info(
            event_name,
            candidate_id=str(candidate.id),
            publisher_id=str(candidate.publisher_id),
            normalized_url=candidate.normalized_url,
            attempt_count=candidate.attempt_count,
            retry_at=_isoformat(retry_at),
            terminal=terminal,
            failure_class=_failure_class(exc),
            failure_reason=_failure_code(exc),
            error_type=type(exc).__name__,
        )


class ArticleWorker:
    def __init__(
        self,
        *,
        repository: ArticleProcessingRepository,
        processor: ArticleProcessor,
        worker_id: str,
        batch_size: int = 20,
        lease_seconds: int = 120,
        concurrency: int = 5,
    ) -> None:
        self._repository = repository
        self._processor = processor
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._concurrency = concurrency

    async def run_once(self) -> int:
        candidates = await self._repository.lease_due_candidates(
            worker_id=self._worker_id,
            limit=min(self._batch_size, self._concurrency),
            lease_seconds=self._lease_seconds,
        )
        semaphore = asyncio.Semaphore(self._concurrency)

        async def run(candidate: LeasedUrlCandidate) -> None:
            async with semaphore:
                stop = asyncio.Event()

                async def keepalive() -> None:
                    interval = max(5.0, self._lease_seconds / 3)
                    while not stop.is_set():
                        try:
                            await asyncio.wait_for(stop.wait(), timeout=interval)
                            return
                        except TimeoutError:
                            ok = await self._repository.heartbeat(
                                candidate_id=candidate.id,
                                worker_id=self._worker_id,
                                lease_version=candidate.lease_version,
                                lease_seconds=self._lease_seconds,
                            )
                            if not ok:
                                return

                heartbeat_task = asyncio.create_task(keepalive())
                try:
                    await self._processor.process(candidate, worker_id=self._worker_id)
                except (OSError, SQLAlchemyError):
                    raise
                except ArticleProcessingError:
                    return
                except Exception:
                    logger.exception(
                        "article_job_failed", candidate_id=str(candidate.id),
                        worker_id=self._worker_id, lease_version=candidate.lease_version,
                    )
                    return
                finally:
                    stop.set()
                    await heartbeat_task

        # Drain every task before retrying a database failure. gather's default
        # early propagation would leave siblings running across leasing rounds.
        outcomes = await asyncio.gather(
            *(run(candidate) for candidate in candidates), return_exceptions=True
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
        return len(candidates)


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _raise_for_unacceptable_extraction(extracted: ExtractedArticle) -> None:
    fatal_warnings = sorted(set(extracted.warnings) & _FATAL_EXTRACTION_WARNINGS)
    # Publicly visible partial text is still useful and should be persisted with
    # warnings. We reject only genuinely unusable extraction, never attempt to
    # bypass subscription or paywall controls.
    if not fatal_warnings:
        return
    quality_score = extracted.metadata.get("extraction_quality_score")
    raise ExtractionQualityError(
        "article extraction rejected: "
        f"fatal_warnings={sorted(set(fatal_warnings))}; "
        f"quality_score={quality_score}; "
        f"word_count={extracted.word_count}"
    )


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, round((completed_at - started_at).total_seconds() * 1_000))


def _candidate_log_context(
    candidate: LeasedUrlCandidate,
    *,
    worker_id: str,
    correlation_id: UUID,
    started_at: datetime,
) -> dict[str, object]:
    return {
        "candidate_id": str(candidate.id),
        "publisher_id": str(candidate.publisher_id),
        "normalized_url": candidate.normalized_url,
        "url": candidate.normalized_url,
        "worker_id": worker_id,
        "attempt_count": candidate.attempt_count,
        "attempt_number": candidate.attempt_count,
        "published_at": _isoformat(candidate.published_at),
        "first_discovered_at": _isoformat(candidate.first_discovered_at),
        "url_type": candidate.url_type,
        "processing_started_at": started_at.isoformat(),
        "correlation_id": str(correlation_id),
    }


def _needs_browser_render(
    extracted: ExtractedArticle,
    *,
    min_word_count: int,
    min_quality: float,
) -> bool:
    quality = _extraction_quality(extracted)
    return (
        not extracted.text_content
        or extracted.word_count < min_word_count
        or quality < min_quality
    )


def _browser_candidate_better(candidate: ExtractedArticle, original: ExtractedArticle) -> bool:
    if not candidate.text_content:
        return False
    candidate_quality = _extraction_quality(candidate)
    original_quality = _extraction_quality(original)
    if not original.text_content:
        return candidate.word_count >= 20
    return (
        candidate.word_count >= max(original.word_count + 30, int(original.word_count * 1.25))
        or candidate_quality >= original_quality + 0.12
    )


def _extraction_quality(extracted: ExtractedArticle) -> float:
    try:
        return max(0.0, min(1.0, float(extracted.metadata.get("extraction_quality_score", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def _unique_domains(values: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        domain = value.casefold().strip().strip(".")
        if domain.startswith("www."):
            domain = domain[4:]
        if domain and domain not in seen:
            seen.add(domain)
            output.append(domain)
    return tuple(output)


def _failure_class(exc: Exception) -> str:
    if isinstance(exc, NonRetryableArticleProcessingError):
        return "permanent"
    return "retryable"


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, ArticleAccessBlockedError):
        return "access_blocked"
    if isinstance(exc, ArticleNotFoundError):
        return "http_permanent"
    if isinstance(exc, ExtractionQualityError):
        return "extraction_quality_rejected"
    if isinstance(exc, InsufficientArticleContentError):
        return "missing_body"
    if isinstance(exc, SQLAlchemyError):
        return "database_error"
    return type(exc).__name__
