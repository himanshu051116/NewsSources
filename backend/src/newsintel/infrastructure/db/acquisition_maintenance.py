from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from newsintel.infrastructure.db.models import PublisherModel, UrlCandidateModel


async def pause_disabled_candidates(session: AsyncSession, now: datetime,
                                    publisher_id: UUID | None = None) -> None:
    disabled = select(PublisherModel.id).where(PublisherModel.active.is_(False))
    if publisher_id is not None:
        disabled = disabled.where(PublisherModel.id == publisher_id)
    await session.execute(update(UrlCandidateModel).where(
        UrlCandidateModel.publisher_id.in_(disabled),
        UrlCandidateModel.state.in_(["ready", "retry", "leased"]),
    ).values(state="paused", processing_stage="paused", lease_owner=None,
             lease_expires_at=None, lease_heartbeat_at=None, current_worker=None,
             lease_version=UrlCandidateModel.lease_version + 1,
             last_error="Publisher disabled; fetching paused.", updated_at=now))
