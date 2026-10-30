from __future__ import annotations

import asyncio
import os
import socket
import uuid

import structlog
from sqlalchemy.exc import SQLAlchemyError

from newsintel.application.briefings.service import GroundedBriefingService
from newsintel.core.config import get_settings
from newsintel.core.logging import configure_logging
from newsintel.infrastructure.db.session import Database


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger("grounded-briefing-worker")
    database = Database(settings)
    service = GroundedBriefingService(database.session_factory)
    worker_id = f"briefing:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    lease_seconds = 90
    failures = 0
    logger.info("grounded_briefing_worker_started", worker_id=worker_id)
    try:
        while True:
            try:
                backfilled = await service.enqueue_missing(limit=100)
                if backfilled:
                    logger.info("grounded_briefing_backfill_queued", count=backfilled)
                stale = await service.enqueue_stale(limit=100)
                if stale:
                    logger.info("grounded_briefing_refresh_queued", count=stale)
                job = await service.lease_next(worker_id=worker_id, lease_seconds=lease_seconds)
                if job is None:
                    failures = 0
                    await asyncio.sleep(2.0)
                    continue
                stop = asyncio.Event()

                async def keepalive() -> None:
                    while not stop.is_set():
                        try:
                            await asyncio.wait_for(stop.wait(), timeout=lease_seconds / 3)
                        except TimeoutError:
                            if not await service.heartbeat(job, worker_id=worker_id, lease_seconds=lease_seconds):
                                return

                task = asyncio.create_task(keepalive())
                try:
                    await service.process(job, worker_id=worker_id)
                except Exception:
                    logger.exception("event_briefing_failed", event_id=str(job.event_id))
                finally:
                    stop.set()
                    await task
                failures = 0
            except (OSError, SQLAlchemyError) as exc:
                failures += 1
                delay = min(float(2 ** min(failures, 8)), settings.database_retry_max_seconds)
                logger.error("briefing_database_unavailable", error_type=type(exc).__name__, retry_in_seconds=delay)
                await asyncio.sleep(delay)
    finally:
        await database.dispose()


def run() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    run()
