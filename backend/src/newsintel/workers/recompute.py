from __future__ import annotations

import asyncio
import os
import socket

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.application.dependencies.service import DerivedArtifactDependencyService
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("derived-recompute-worker")
    database = Database(settings)
    service = DerivedArtifactDependencyService(database.session_factory)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info("derived_recompute_worker_started", worker_id=worker_id)
    database_failures = 0
    try:
        while True:
            try:
                jobs = await service.lease_jobs(
                    worker_id=worker_id,
                    # Dispatch is sequential. Claim only work we can start now.
                    limit=1,
                    lease_seconds=settings.derived_recompute_lease_seconds,
                )
                for job in jobs:
                    try:
                        await service.dispatch(job)
                    except (OSError, SQLAlchemyError):
                        raise
                    except Exception as exc:
                        await service.fail(job, exc)
                        logger.exception(
                            "derived_recompute_dispatch_failed",
                            job_id=str(job.id),
                            artifact_kind=job.artifact_kind,
                            artifact_id=str(job.artifact_id),
                            error_type=type(exc).__name__,
                        )
                if database_failures:
                    logger.info("database_connection_restored")
                    database_failures = 0
            except (OSError, SQLAlchemyError) as exc:
                database_failures += 1
                delay = min(float(2 ** min(database_failures, 10)), settings.database_retry_max_seconds)
                logger.error("database_unavailable", error_type=type(exc).__name__, retry_in_seconds=delay)
                await asyncio.sleep(delay)
                continue
            if not jobs:
                await asyncio.sleep(settings.derived_recompute_idle_seconds)
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
