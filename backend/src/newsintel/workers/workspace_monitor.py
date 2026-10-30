from __future__ import annotations

import asyncio
import os
import socket

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.application.workspace_monitor_service import WorkspaceMonitorService
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database


def database_retry_delay(attempt: int, maximum_seconds: float) -> float:
    return min(maximum_seconds, float(2 ** min(attempt, 10)))


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("workspace-monitor-worker")
    database = Database(settings)
    service = WorkspaceMonitorService(database.session_factory)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    database_failure_attempt = 0
    logger.info("workspace_monitor_worker_started", worker_id=worker_id)
    try:
        while True:
            try:
                leases = await service.lease_due(
                    worker_id=worker_id,
                    # Runs are sequential; do not hold unstarted leases.
                    limit=1,
                    lease_seconds=settings.workspace_monitor_lease_seconds,
                )
                for lease in leases:
                    try:
                        await service.execute(lease)
                    except (OSError, SQLAlchemyError):
                        raise
                    except Exception as exc:
                        await service.fail(lease, exc)
                        logger.exception(
                            "workspace_monitor_run_failed",
                            monitor_id=str(lease.id),
                            target_type=lease.target_type,
                            target_id=str(lease.target_id),
                            lease_version=lease.lease_version,
                            error_type=type(exc).__name__,
                        )
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

            if not leases:
                await asyncio.sleep(settings.workspace_monitor_idle_seconds)
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
