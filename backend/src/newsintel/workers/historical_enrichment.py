import asyncio
import os
import socket

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.adapters.semantic.local import OllamaEmbeddingClient, QdrantSemanticIndex
from newsintel.application.historical.enrichment_service import (
    HistoricalEnrichmentService,
    LeasedHistoricalEnrichmentJob,
)
from newsintel.application.historical.semantic_service import SemanticHistoryService
from newsintel.application.historical.runtime import build_historical_search_runtime
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database


def database_retry_delay(attempt: int, maximum_seconds: float) -> float:
    return min(maximum_seconds, float(2 ** min(attempt, 10)))


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("historical-enrichment-worker")
    database = Database(settings)
    runtime = (
        build_historical_search_runtime(settings)
        if settings.historical_enrichment_external_enabled and settings.historical_search_enabled
        else None
    )
    semantic_service = None
    if settings.semantic_search_enabled:
        if settings.ai_provider != "local":
            logger.warning(
                "semantic_search_disabled_without_local_ai",
                hint="Set NEWSINTEL_AI_PROVIDER=local or disable semantic search.",
            )
        else:
            semantic_service = SemanticHistoryService(
                database.session_factory,
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
                model=settings.semantic_embedding_model,
            )

    service = HistoricalEnrichmentService(
        database.session_factory,
        external_service=runtime.service if runtime else None,
        external_enabled=bool(runtime),
        semantic_service=semantic_service,
        semantic_limit=settings.semantic_search_limit,
        max_queries=settings.historical_enrichment_max_queries,
        internal_limit=settings.historical_enrichment_internal_limit,
        external_limit_per_query=settings.historical_enrichment_external_limit_per_query,
        max_attempts=settings.historical_enrichment_max_attempts,
    )
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info(
        "historical_enrichment_worker_started",
        worker_id=worker_id,
        external_enabled=bool(runtime),
        semantic_enabled=semantic_service is not None,
        enabled=settings.historical_enrichment_enabled,
    )
    if not settings.historical_enrichment_enabled:
        logger.warning("historical_enrichment_disabled")
        try:
            while True:
                await asyncio.sleep(60)
        finally:
            if runtime is not None:
                await runtime.aclose()
            await database.dispose()
        return
    database_failure_attempt = 0
    try:
        while True:
            try:
                if semantic_service is not None:
                    try:
                        indexed = await semantic_service.index_missing(
                            limit=settings.semantic_index_batch_size
                        )
                        if indexed:
                            logger.info("semantic_article_versions_indexed", count=indexed)
                    except Exception as exc:
                        logger.warning(
                            "semantic_indexing_unavailable",
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:300],
                        )
                backfilled = await service.enqueue_missing_jobs(
                    limit=settings.historical_enrichment_batch_size * 5
                )
                if backfilled:
                    logger.info("historical_enrichment_backfill_queued", count=backfilled)
                reconciled = await service.requeue_stale_contexts(
                    limit=settings.historical_enrichment_batch_size * 5
                )
                if reconciled:
                    logger.info(
                        "historical_enrichment_reconciliation_queued",
                        count=reconciled,
                    )
                semantic_requeued = await service.requeue_missing_semantic_contexts(
                    limit=settings.historical_enrichment_batch_size * 2
                )
                if semantic_requeued:
                    logger.info(
                        "historical_semantic_reconciliation_queued",
                        count=semantic_requeued,
                    )
                jobs = await service.lease_due_jobs(
                    worker_id=worker_id,
                    limit=min(
                        settings.historical_enrichment_batch_size,
                        settings.historical_enrichment_concurrency,
                    ),
                    lease_seconds=settings.historical_enrichment_lease_seconds,
                )
                if jobs:
                    semaphore = asyncio.Semaphore(settings.historical_enrichment_concurrency)

                    async def _process(job: LeasedHistoricalEnrichmentJob) -> None:
                        async with semaphore:
                            stop = asyncio.Event()

                            async def keepalive() -> None:
                                while not stop.is_set():
                                    try:
                                        await asyncio.wait_for(
                                            stop.wait(),
                                            timeout=max(5.0, settings.historical_enrichment_lease_seconds / 3),
                                        )
                                    except TimeoutError:
                                        try:
                                            if not await service.heartbeat(job, lease_seconds=settings.historical_enrichment_lease_seconds):
                                                logger.warning("historical_enrichment_lease_lost", job_id=str(job.id))
                                                return
                                        except Exception:
                                            logger.exception("historical_enrichment_heartbeat_failed", job_id=str(job.id))
                                            return

                            heartbeat_task = asyncio.create_task(keepalive())
                            try:
                                await service.process(job)
                            except Exception:
                                # The service has already attempted to persist retry/failure state.
                                logger.exception("historical_enrichment_process_failed", job_id=str(job.id))
                            finally:
                                stop.set()
                                await heartbeat_task

                    await asyncio.gather(*(_process(job) for job in jobs))
                if database_failure_attempt:
                    logger.info("database_connection_restored")
                    database_failure_attempt = 0
            except (OSError, SQLAlchemyError) as exc:
                database_failure_attempt += 1
                delay = database_retry_delay(
                    database_failure_attempt,
                    settings.database_retry_max_seconds,
                )
                logger.error(
                    "database_unavailable",
                    error_type=type(exc).__name__,
                    retry_in_seconds=delay,
                    hint="Run: python -m newsintel.doctor",
                )
                await asyncio.sleep(delay)
                continue
            if not jobs:
                await asyncio.sleep(settings.historical_enrichment_idle_seconds)
    finally:
        if runtime is not None:
            await runtime.aclose()
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
