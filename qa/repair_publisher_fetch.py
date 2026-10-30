"""Review/repair legacy archive scans, retaining all articles and discovery rows."""
import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select, update

from newsintel.core.config import get_settings
from newsintel.domain.acquisition.scheduling import current_sitemap
from newsintel.infrastructure.db.acquisition_maintenance import pause_disabled_candidates
from newsintel.infrastructure.db.models import DiscoveryChannelModel as Channel
from newsintel.infrastructure.db.models import FetchJobModel as Job
from newsintel.infrastructure.db.models import PublisherModel as Publisher
from newsintel.infrastructure.db.models import UrlCandidateModel as Candidate
from newsintel.infrastructure.db.session import Database


async def repair(apply=False):
    now = datetime.now(UTC)
    database = Database(get_settings())
    try:
        async with database.session_factory() as session, session.begin():
            rows = (await session.execute(select(Channel, Publisher.name)
                    .join(Publisher, Publisher.id == Channel.publisher_id)
                    .where(Channel.active.is_(True), Publisher.active.is_(True)))).all()
            archives = [row for row, _ in rows if row.channel_type in {"sitemap", "news_sitemap"}
                        and not current_sitemap(row.endpoint_url, now,
                                                get_settings().recent_article_window_hours)]
            pending_by_job = Counter(row.fetch_job_id for row, _ in rows if row.fetch_job_id)
            candidates = list((await session.scalars(select(Candidate).where(
                Candidate.publisher_id.in_(select(Publisher.id).where(Publisher.active.is_(False))),
                Candidate.state.in_(["ready", "retry", "leased"]),
            ))).all())
            jobs = list((await session.scalars(select(Job).where(
                Job.status.in_(["scheduled", "running", "processing_articles"]),
            ))).all())
            cancelled = []
            for job in jobs:
                oversized = pending_by_job[job.id] > 20 * max(1, job.publishers_total)
                pending = await session.scalar(select(func.count(Candidate.id)).where(
                    Candidate.originating_fetch_job_id == job.id,
                    Candidate.state.in_(["ready", "retry", "leased"])))
                orphaned = (not pending_by_job[job.id] and not pending
                            and job.created_at < now - timedelta(hours=1))
                if oversized or orphaned:
                    cancelled.append(job)
            names = {row.id: name for row, name in rows}
            report = {"apply": apply, "archives_paused": len(archives),
                      "disabled_candidates_paused": len(candidates),
                      "legacy_jobs_cancelled": len(cancelled),
                      "archive_publishers": dict(Counter(names[row.id] for row in archives)),
                      "archive_examples": [row.endpoint_url for row in archives[:8]]}
            if apply:
                root = Path(__file__).resolve().parents[1]
                backup = root / ".run" / "backups" / ("publisher-fetch-repair-" + now.strftime("%Y%m%dT%H%M%S") + ".json")
                original = {"generated_at": now, "channels": [
                    {column.key: getattr(row, "metadata_" if column.key == "metadata" else column.key)
                     for column in row.__table__.columns} for row, _ in rows],
                    "candidates": [{column.key: getattr(row, column.key)
                                    for column in row.__table__.columns} for row in candidates],
                    "jobs": [{column.key: getattr(row, "metadata_" if column.key == "metadata" else column.key)
                              for column in row.__table__.columns} for row in cancelled]}
                backup.write_text(json.dumps(original, default=str), encoding="utf-8")
                for start in range(0, len(archives), 1000):
                    await session.execute(update(Channel).where(Channel.id.in_(
                        [row.id for row in archives[start:start+1000]],
                    )).values(active=False, fetch_job_id=None, lease_owner=None,
                              lease_expires_at=None, lease_heartbeat_at=None,
                              lease_version=Channel.lease_version+1,
                              config=Channel.config.op("||")({"scheduling_paused_reason":
                                      "dated_archive_outside_recent_window"}), updated_at=now),
                              execution_options={"synchronize_session": False})
                ids = [job.id for job in cancelled]
                if ids:
                    await session.execute(update(Channel).where(Channel.fetch_job_id.in_(ids))
                                          .values(fetch_job_id=None))
                    await session.execute(update(Job).where(Job.id.in_(ids)).values(
                        status="cancelled", completed_at=now, updated_at=now,
                        message="Legacy archive scan stopped. Start a new bounded fetch of current news."))
                await pause_disabled_candidates(session, now)
                await session.execute(update(Channel).where(Channel.active.is_(True),
                    Channel.publisher_id.in_(select(Publisher.id).where(Publisher.active.is_(True))),
                    Channel.channel_type.in_(["rss", "atom", "json_feed", "news_sitemap", "homepage"]),
                ).values(next_poll_at=now, updated_at=now))
                report["backup"] = str(backup)
            print(json.dumps(report, indent=2))
            return report
    finally:
        await database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(repair(parser.parse_args().apply))
