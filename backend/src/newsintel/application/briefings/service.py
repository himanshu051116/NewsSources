from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.historical_enrichment import normalize_history_url
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleCorrectionEventModel,
    ArticleHistoricalContextModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimEvidenceLinkModel,
    ClaimVerificationModel,
    EventBriefingJobModel,
    EventBriefingModel,
    EventModel,
    PublisherModel,
)

logger = structlog.get_logger(__name__)
BRIEFING_METHODOLOGY_VERSION = "grounded-event-briefing-v1"


@dataclass(frozen=True, slots=True)
class LeasedBriefingJob:
    id: UUID
    event_id: UUID
    trigger_article_version_id: UUID
    lease_version: int
    attempt_count: int


class GroundedBriefingService:
    """Builds evidence-grounded event explanations from stored platform records only.

    The service deliberately does not use model/world knowledge. Every factual item in the
    briefing is derived from a stored event/article/claim/history/correction record and keeps
    explicit evidence references.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, max_attempts: int = 3) -> None:
        self._session_factory = session_factory
        self._max_attempts = max_attempts

    async def enqueue_stale(self, *, limit: int = 100) -> int:
        """Queue event briefings when current articles, verifications, corrections or history changed."""
        now = datetime.now(UTC)
        briefing_latest = (
            select(EventBriefingModel.event_id, func.max(EventBriefingModel.generated_at).label("briefed_at"))
            .group_by(EventBriefingModel.event_id).subquery()
        )
        verification_latest = (
            select(ArticleModel.event_id, func.max(ClaimVerificationModel.created_at).label("verified_at"))
            .join(ArticleClaimModel, ArticleClaimModel.id == ClaimVerificationModel.claim_id)
            .join(ArticleModel, ArticleModel.id == ArticleClaimModel.article_id)
            .group_by(ArticleModel.event_id).subquery()
        )
        history_latest = (
            select(ArticleHistoricalContextModel.event_id, func.max(ArticleHistoricalContextModel.generated_at).label("history_at"))
            .group_by(ArticleHistoricalContextModel.event_id).subquery()
        )
        correction_latest = (
            select(ArticleCorrectionEventModel.event_id, func.max(ArticleCorrectionEventModel.created_at).label("correction_at"))
            .group_by(ArticleCorrectionEventModel.event_id).subquery()
        )
        async with self._session_factory() as session, session.begin():
            rows = (await session.execute(
                select(EventModel.id)
                .join(briefing_latest, briefing_latest.c.event_id == EventModel.id)
                .outerjoin(verification_latest, verification_latest.c.event_id == EventModel.id)
                .outerjoin(history_latest, history_latest.c.event_id == EventModel.id)
                .outerjoin(correction_latest, correction_latest.c.event_id == EventModel.id)
                .where(
                    func.greatest(
                        EventModel.updated_at,
                        func.coalesce(verification_latest.c.verified_at, EventModel.created_at),
                        func.coalesce(history_latest.c.history_at, EventModel.created_at),
                        func.coalesce(correction_latest.c.correction_at, EventModel.created_at),
                    ) > briefing_latest.c.briefed_at
                )
                .order_by(EventModel.updated_at.desc()).limit(max(1, min(limit, 500)))
            )).scalars().all()
            queued = 0
            for event_id in rows:
                version_id = (await session.execute(
                    select(ArticleVersionModel.id).join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                    .where(ArticleModel.event_id == event_id)
                    .order_by(ArticleVersionModel.retrieved_at.desc()).limit(1)
                )).scalar_one_or_none()
                if version_id is None:
                    continue
                stmt = insert(EventBriefingJobModel).values(
                    id=uuid7(), event_id=event_id, trigger_article_version_id=version_id, state="queued",
                    attempt_count=0, next_attempt_at=now, created_at=now, updated_at=now,
                )
                result = await session.execute(stmt.on_conflict_do_update(
                    constraint="uq_event_briefing_job_event",
                    set_={
                        "trigger_article_version_id": version_id, "state": "queued", "attempt_count": 0,
                        "next_attempt_at": now, "last_error": None, "completed_at": None,
                        "lease_owner": None, "lease_expires_at": None, "lease_heartbeat_at": None,
                        "updated_at": now,
                    },
                    where=(EventBriefingJobModel.state != "running") | (EventBriefingJobModel.lease_expires_at < now),
                ))
                # An active lease intentionally skips this upsert; do not count it as queued.
                queued += int(result.rowcount or 0)
            return queued

    async def enqueue_missing(self, *, limit: int = 100) -> int:
        """Backfill one briefing job per event that already has historical context."""
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            rows = (await session.execute(
                select(ArticleHistoricalContextModel.event_id, ArticleHistoricalContextModel.article_version_id)
                .where(~ArticleHistoricalContextModel.event_id.in_(select(EventBriefingJobModel.event_id)))
                .order_by(ArticleHistoricalContextModel.generated_at.desc())
                .limit(max(1, min(limit, 1000)))
            )).all()
            seen: set[UUID] = set(); count = 0
            for event_id, version_id in rows:
                if event_id in seen:
                    continue
                seen.add(event_id)
                inserted = await session.execute(
                    insert(EventBriefingJobModel).values(
                        id=uuid7(), event_id=event_id, trigger_article_version_id=version_id,
                        state="queued", attempt_count=0, next_attempt_at=now, created_at=now, updated_at=now,
                    ).on_conflict_do_nothing(constraint="uq_event_briefing_job_event")
                )
                count += int(inserted.rowcount or 0)
            return count

    async def enqueue(self, *, event_id: UUID, trigger_article_version_id: UUID) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            stmt = insert(EventBriefingJobModel).values(
                id=uuid7(), event_id=event_id, trigger_article_version_id=trigger_article_version_id,
                state="queued", attempt_count=0, next_attempt_at=now, created_at=now, updated_at=now,
            )
            await session.execute(stmt.on_conflict_do_update(
                constraint="uq_event_briefing_job_event",
                set_={
                    "trigger_article_version_id": trigger_article_version_id,
                    "state": "queued", "attempt_count": 0, "next_attempt_at": now,
                    "last_error": None, "completed_at": None,
                    "lease_owner": None, "lease_expires_at": None, "lease_heartbeat_at": None,
                    "updated_at": now,
                },
                where=(EventBriefingJobModel.state != "running") | (EventBriefingJobModel.lease_expires_at < now),
            ))

    async def lease_next(self, *, worker_id: str, lease_seconds: int = 90) -> LeasedBriefingJob | None:
        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=max(15, lease_seconds))
        async with self._session_factory() as session, session.begin():
            row = (await session.execute(
                select(EventBriefingJobModel)
                .where(or_(
                    and_(
                        EventBriefingJobModel.state.in_(("queued", "retry")),
                        EventBriefingJobModel.next_attempt_at <= now,
                        or_(EventBriefingJobModel.lease_expires_at.is_(None), EventBriefingJobModel.lease_expires_at < now),
                    ),
                    and_(
                        EventBriefingJobModel.state == "running",
                        EventBriefingJobModel.lease_expires_at < now,
                    ),
                ))
                .order_by(EventBriefingJobModel.next_attempt_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )).scalar_one_or_none()
            if row is None:
                return None
            row.state = "running"
            row.attempt_count += 1
            row.lease_owner = worker_id
            row.lease_version += 1
            row.lease_expires_at = expiry
            row.lease_heartbeat_at = now
            row.started_at = now
            row.updated_at = now
            return LeasedBriefingJob(row.id, row.event_id, row.trigger_article_version_id, row.lease_version, row.attempt_count)

    async def heartbeat(self, job: LeasedBriefingJob, *, worker_id: str, lease_seconds: int = 90) -> bool:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(EventBriefingJobModel)
                .where(
                    EventBriefingJobModel.id == job.id,
                    EventBriefingJobModel.lease_owner == worker_id,
                    EventBriefingJobModel.lease_version == job.lease_version,
                    EventBriefingJobModel.state == "running",
                    EventBriefingJobModel.lease_expires_at > now,
                )
                .values(lease_heartbeat_at=now, lease_expires_at=now + timedelta(seconds=max(15, lease_seconds)), updated_at=now)
            )
            return bool(result.rowcount)

    async def process(self, job: LeasedBriefingJob, *, worker_id: str) -> dict[str, Any]:
        try:
            payload, refs, digest = await self._build(job.event_id, job.trigger_article_version_id)
            now = datetime.now(UTC)
            async with self._session_factory() as session, session.begin():
                owned = (await session.execute(select(EventBriefingJobModel).where(
                    EventBriefingJobModel.id == job.id,
                    EventBriefingJobModel.lease_owner == worker_id,
                    EventBriefingJobModel.lease_version == job.lease_version,
                    EventBriefingJobModel.state == "running",
                    EventBriefingJobModel.lease_expires_at > now,
                ).with_for_update())).scalar_one_or_none()
                if owned is None:
                    raise RuntimeError("briefing lease lost before completion")
                stmt = insert(EventBriefingModel).values(
                    id=uuid7(), event_id=job.event_id, trigger_article_version_id=job.trigger_article_version_id,
                    methodology_version=BRIEFING_METHODOLOGY_VERSION, evidence_pack_sha256=digest,
                    payload=payload, evidence_refs=refs, generated_at=now, created_at=now,
                )
                await session.execute(stmt.on_conflict_do_nothing(constraint="uq_event_briefing_evidence_pack"))
                owned.state = "succeeded"; owned.completed_at = now; owned.last_error = None
                owned.lease_owner = None; owned.lease_expires_at = None; owned.lease_heartbeat_at = None; owned.updated_at = now
            return payload
        except Exception as exc:
            await self._fail(job, worker_id=worker_id, exc=exc)
            raise

    async def latest(self, event_id: UUID) -> EventBriefingModel | None:
        async with self._session_factory() as session:
            return (await session.execute(
                select(EventBriefingModel).where(EventBriefingModel.event_id == event_id)
                .order_by(EventBriefingModel.generated_at.desc()).limit(1)
            )).scalar_one_or_none()

    async def rebuild_now(self, event_id: UUID) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            version_id = (await session.execute(
                select(ArticleVersionModel.id)
                .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                .where(ArticleModel.event_id == event_id)
                .order_by(ArticleVersionModel.retrieved_at.desc()).limit(1)
            )).scalar_one_or_none()
        if version_id is None:
            return None
        payload, refs, digest = await self._build(event_id, version_id)
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            stmt = insert(EventBriefingModel).values(
                id=uuid7(), event_id=event_id, trigger_article_version_id=version_id,
                methodology_version=BRIEFING_METHODOLOGY_VERSION, evidence_pack_sha256=digest,
                payload=payload, evidence_refs=refs, generated_at=now, created_at=now,
            )
            await session.execute(stmt.on_conflict_do_nothing(constraint="uq_event_briefing_evidence_pack"))
        return payload

    async def _build(self, event_id: UUID, trigger_version_id: UUID) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                raise LookupError(f"event not found: {event_id}")
            latest_versions = select(
                ArticleVersionModel.article_id, func.max(ArticleVersionModel.version_number).label("vn")
            ).join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id).where(
                ArticleModel.event_id == event_id
            ).group_by(ArticleVersionModel.article_id).subquery()
            article_rows = (await session.execute(
                select(ArticleModel, ArticleVersionModel, PublisherModel)
                .join(latest_versions, latest_versions.c.article_id == ArticleModel.id)
                .join(ArticleVersionModel, and_(ArticleVersionModel.article_id == ArticleModel.id, ArticleVersionModel.version_number == latest_versions.c.vn))
                .join(PublisherModel, PublisherModel.id == ArticleModel.publisher_id)
                .where(ArticleModel.event_id == event_id)
                .order_by(func.coalesce(ArticleVersionModel.published_at, ArticleVersionModel.retrieved_at).desc()).limit(30)
            )).all()
            version_ids = [v.id for _, v, _ in article_rows]
            claims = []
            if version_ids:
                claims = list((await session.execute(
                    select(ArticleClaimModel).where(ArticleClaimModel.article_version_id.in_(version_ids)).order_by(ArticleClaimModel.created_at.desc()).limit(100)
                )).scalars())
            claim_ids = [c.id for c in claims]
            verifications: dict[UUID, ClaimVerificationModel] = {}
            if claim_ids:
                rows = (await session.execute(
                    select(ClaimVerificationModel).where(ClaimVerificationModel.claim_id.in_(claim_ids))
                    .order_by(ClaimVerificationModel.claim_id, ClaimVerificationModel.created_at.desc())
                )).scalars().all()
                for row in rows:
                    verifications.setdefault(row.claim_id, row)
            evidence_by_claim: dict[UUID, list[ClaimEvidenceLinkModel]] = {}
            if claim_ids:
                evidence_links = (await session.execute(
                    select(ClaimEvidenceLinkModel).where(
                        ClaimEvidenceLinkModel.claim_id.in_(claim_ids)
                    ).order_by(
                        ClaimEvidenceLinkModel.claim_id,
                        ClaimEvidenceLinkModel.retrieved_at.desc(),
                    )
                )).scalars().all()
                for link in evidence_links:
                    evidence_by_claim.setdefault(link.claim_id, []).append(link)
            historical = (await session.execute(
                select(ArticleHistoricalContextModel).where(ArticleHistoricalContextModel.event_id == event_id)
                .order_by(ArticleHistoricalContextModel.generated_at.desc()).limit(1)
            )).scalar_one_or_none()
            corrections = list((await session.execute(
                select(ArticleCorrectionEventModel).where(ArticleCorrectionEventModel.event_id == event_id)
                .order_by(ArticleCorrectionEventModel.created_at.desc()).limit(20)
            )).scalars())

        refs: list[dict[str, Any]] = []
        articles = []
        for a, v, p in article_rows:
            ref = f"article_version:{v.id}"
            refs.append({"id": ref, "kind": "article_version", "record_id": str(v.id), "url": v.final_url, "title": v.title, "publisher": p.name})
            articles.append({"ref": ref, "article_id": str(a.id), "version_id": str(v.id), "title": v.title, "publisher": p.name, "published_at": _iso(v.published_at or v.retrieved_at)})

        supported, disputed, unresolved = [], [], []
        for c in claims:
            vr = verifications.get(c.id)
            label = (vr.label if vr else "unverified").casefold()
            links = evidence_by_claim.get(c.id, [])
            supporting_links = [
                x for x in links if x.relationship.casefold() in {"support", "supports", "supported"}
            ]
            reference_ids = [f"claim:{c.id}"]
            # The claim record is the asserted proposition, NOT its corroborating source.
            refs.append({"id": f"claim:{c.id}", "kind": "claim", "record_id": str(c.id),
                         "text": c.claim_text, "title": "Recorded claim (not independent evidence)"})
            # Prefer citing actual supporting passages before newer but unrelated or
            # contradictory links. A supported label must have a traceable support citation.
            ordered_links = sorted(
                links,
                key=lambda link: (
                    link.relationship.casefold() not in {"support", "supports", "supported"},
                    link.source_type.casefold() not in {"official_document", "primary_document", "primary_source"},
                    -(link.retrieved_at.timestamp() if link.retrieved_at is not None else 0),
                ),
            )
            for link in ordered_links[:8]:
                ref = f"evidence_link:{link.id}"
                reference_ids.append(ref)
                refs.append({"id": ref, "kind": "evidence_link", "record_id": str(link.id),
                             "url": link.source_url, "title": "Evidence source — " + link.relationship,
                             "relationship": link.relationship, "source_type": link.source_type})
            item = {"text": c.claim_text, "claim_id": str(c.id), "verification": label,
                    "evidence_link_count": len(links), "evidence_ids": reference_ids}
            # A supported decision without a traceable supporting link should not appear
            # as an evidence-backed finding in the published briefing.
            if label == "supported" and supporting_links:
                supported.append(item)
            elif label in {"contradicted", "disputed", "misleading"}:
                disputed.append(item)
            else:
                if label == "supported" and not supporting_links:
                    item["evidence_trace_warning"] = "Stored support decision has no linked supporting evidence"
                unresolved.append(item)

        history_items: list[dict[str, Any]] = []
        context_summary: dict[str, Any] = {}
        if historical is not None:
            refs.append({"id": f"historical_context:{historical.id}", "kind": "historical_context", "record_id": str(historical.id)})
            context_summary = dict(historical.context_summary or {})
            merged = [*(historical.same_event_history or []), *(historical.internal_matches or []), *(historical.external_matches or [])]
            history_items = _briefing_history_items(merged, cutoff=historical.cutoff_at, limit=12)
            for index, item in enumerate(history_items):
                ref = f"history:{historical.id}:{index}"
                item["ref"] = ref
                refs.append({"id": ref, "kind": "historical_item", "url": item.get("url"), "title": item.get("title")})

        correction_items = []
        for corr in corrections:
            ref = f"correction:{corr.id}"
            refs.append({"id": ref, "kind": "correction", "record_id": str(corr.id), "url": corr.source_url})
            correction_items.append({"kind": corr.correction_kind, "note": corr.note, "created_at": _iso(corr.created_at), "evidence_ids": [ref]})

        headline_refs = [a["ref"] for a in articles[:3]]
        what_happened = {
            "text": f"This briefing reviews {len(articles)} of the latest linked report{'s' if len(articles) != 1 else ''} about “{event.title}” (at most 30 reports are included; this is not a complete source count).",
            "evidence_ids": headline_refs,
        }
        latest_titles = [{"title": a["title"], "publisher": a["publisher"], "published_at": a["published_at"], "evidence_ids": [a["ref"]]} for a in articles[:5]]
        changed_count = int(context_summary.get("changed_claim_family_count") or 0)
        numeric_count = int(context_summary.get("numeric_change_family_count") or 0)
        temporal_count = int(context_summary.get("temporal_change_family_count") or 0)
        pattern = str(context_summary.get("change_pattern") or "unknown")
        what_changed = {
            "text": (
                f"The latest stored article-level historical comparison is classified as {pattern.replace('_', ' ')}. "
                f"Within that comparison, {changed_count} claim families changed, including {numeric_count} numerical "
                f"and {temporal_count} time-related changes. These are not event-wide totals."
                if historical else
                "No historical comparison is available yet. Changes cannot be assessed from the stored context."
            ),
            "evidence_ids": [f"historical_context:{historical.id}"] if historical else [],
        }
        why_it_matters = {
            "text": (
                "The available records show changes to reporting, but do not establish the "
                "event's real-world consequences. Read the primary sources and distinguish "
                "published claims from independently supported findings."
            ),
            "label": "impact_not_assessed",
            "evidence_ids": [],
        }
        payload: dict[str, Any] = {
            "event": {"id": str(event.id), "title": event.title, "lifecycle_status": event.lifecycle_status, "first_detected_at": _iso(event.first_detected_at), "last_material_change_at": _iso(event.last_material_change_at)},
            "what_happened": what_happened,
            "latest_reporting": latest_titles,
            "what_changed": what_changed,
            "historical_background": history_items,
            "established_facts": supported[:12],
            "disputed_or_contradicted": disputed[:12],
            "unresolved_or_insufficient_evidence": unresolved[:12],
            "corrections": correction_items,
            "why_it_matters": why_it_matters,
            "source_diversity_count": context_summary.get("source_diversity_count"),
            "historical_depth": context_summary.get("historical_depth"),
            "methodology": {
                "version": BRIEFING_METHODOLOGY_VERSION,
                "grounding_rule": "Only stored platform records are used. Missing support is represented as uncertainty rather than filled from model/world knowledge.",
                "trigger_article_version_id": str(trigger_version_id),
            },
        }
        canonical = json.dumps({"payload": payload, "refs": refs}, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return payload, refs, digest

    async def _fail(self, job: LeasedBriefingJob, *, worker_id: str, exc: Exception) -> None:
        now = datetime.now(UTC); retry = job.attempt_count < self._max_attempts
        async with self._session_factory() as session, session.begin():
            row = (await session.execute(select(EventBriefingJobModel).where(
                EventBriefingJobModel.id == job.id, EventBriefingJobModel.lease_owner == worker_id,
                EventBriefingJobModel.lease_version == job.lease_version,
                EventBriefingJobModel.state == "running").with_for_update())).scalar_one_or_none()
            if row is None: return
            row.state = "retry" if retry else "failed"; row.last_error = str(exc)[:4000]
            row.next_attempt_at = now + timedelta(seconds=min(300, 15 * (2 ** max(0, job.attempt_count - 1))))
            row.lease_owner = None; row.lease_expires_at = None; row.lease_heartbeat_at = None; row.updated_at = now


def _history_date(value: object) -> datetime | None:
    if isinstance(value, datetime):
        date = value
    elif isinstance(value, str):
        try:
            date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=UTC)
    return date.astimezone(UTC)


def _briefing_history_items(
    items: list[dict[str, Any]], *, cutoff: datetime, limit: int = 12
) -> list[dict[str, Any]]:
    """Sort historical citations by dated evidence, collapse tracking-URL duplicates,
    and reject records known to postdate the historical cutoff.

    An observation date is not misrepresented as the publication date.
    Undated records remain visible only after dated records.
    """
    earlier: list[tuple[datetime | None, dict[str, Any]]] = []
    seen: set[str] = set()
    cutoff_utc = cutoff.astimezone(UTC) if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        published = _history_date(item.get("published_at"))
        observed = _history_date(item.get("observed_at"))
        effective = published or observed
        if effective is not None and effective >= cutoff_utc:
            continue
        url = item.get("url") or item.get("source_url")
        key = normalize_history_url(url) or str(item.get("article_version_id") or item.get("id") or f"row-{idx}")
        if key in seen:
            continue
        seen.add(key)
        earlier.append((effective, {
            "title": item.get("title") or "Earlier report",
            "source": item.get("source_name") or item.get("publisher_name") or item.get("publisher") or item.get("provider"),
            "published_at": published.isoformat() if published else None,
            "observed_at": observed.isoformat() if observed else None,
            "date_basis": "publication" if published else ("observation" if observed else "unknown"),
            "url": url,
        }))
    # Present history as a timeline from earliest to latest; undated context follows.
    earlier.sort(key=lambda pair: pair[0] or datetime.max.replace(tzinfo=UTC))
    return [item for _, item in earlier[:max(0, limit)]]


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value else None
