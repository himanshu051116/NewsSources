from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from newsintel.application.dependencies.service import (
    HISTORICAL_CONTEXT_ARTIFACT,
    DependencySource,
    DerivedArtifactDependencyService,
)
from newsintel.application.historical.dto import HistoricalSearchCommand
from newsintel.application.historical.semantic_service import SemanticHistoryService
from newsintel.application.historical.service import HistoricalSearchService
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.historical_enrichment import (
    HISTORICAL_ENRICHMENT_VERSION,
    build_historical_queries,
    classify_claim_evolution,
    deduplicate_history_items,
    historical_context_confidence,
    historical_depth,
    historical_relevance_score,
    normalize_history_url,
    summarize_change_pattern,
    timeline_summary,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleHistoricalContextModel,
    ArticleHistoricalEnrichmentJobModel,
    ArticleModel,
    ArticleVersionModel,
    EventBriefingJobModel,
    ClaimVerificationModel,
    PublisherModel,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LeasedHistoricalEnrichmentJob:
    id: UUID
    article_id: UUID
    article_version_id: UUID
    event_id: UUID
    cutoff_at: datetime
    attempt_count: int
    # Identifies the exact leased attempt without requiring a database migration.
    # Existing unit/replay constructors can omit these; real worker leases always set them.
    lease_owner: str | None = None
    lease_started_at: datetime | None = None


class HistoricalEnrichmentService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        external_service: HistoricalSearchService | None = None,
        external_enabled: bool = False,
        semantic_service: SemanticHistoryService | None = None,
        semantic_limit: int = 20,
        max_queries: int = 3,
        internal_limit: int = 25,
        external_limit_per_query: int = 15,
        max_attempts: int = 3,
    ) -> None:
        self._session_factory = session_factory
        self._dependencies = DerivedArtifactDependencyService(session_factory)
        self._external_service = external_service
        self._external_enabled = external_enabled and external_service is not None
        self._semantic_service = semantic_service
        self._semantic_limit = max(1, min(semantic_limit, 100))
        self._max_queries = max_queries
        self._internal_limit = internal_limit
        self._external_limit_per_query = external_limit_per_query
        self._max_attempts = max_attempts

    async def enqueue_missing_jobs(self, *, limit: int = 100) -> int:
        """Backfill enrichment jobs for article versions created before this feature existed."""
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.execute(
                    select(ArticleVersionModel, ArticleModel)
                    .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                    .outerjoin(
                        ArticleHistoricalEnrichmentJobModel,
                        ArticleHistoricalEnrichmentJobModel.article_version_id
                        == ArticleVersionModel.id,
                    )
                    .where(ArticleHistoricalEnrichmentJobModel.id.is_(None))
                    .order_by(ArticleVersionModel.created_at.desc())
                    .limit(limit)
                )
            ).all()
            inserted = 0
            for version, article in rows:
                result = await session.execute(
                    insert(ArticleHistoricalEnrichmentJobModel)
                    .values(
                        id=uuid7(),
                        article_id=article.id,
                        article_version_id=version.id,
                        event_id=article.event_id,
                        state="queued",
                        attempt_count=0,
                        refresh_count=0,
                        last_refresh_reason=None,
                        last_reconciled_at=None,
                        next_attempt_at=now,
                        lease_owner=None,
                        lease_expires_at=None,
                        cutoff_at=version.retrieved_at,
                        query_terms=[],
                        last_error=None,
                        started_at=None,
                        completed_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_historical_enrichment_job_version"
                    )
                    .returning(ArticleHistoricalEnrichmentJobModel.id)
                )
                if result.scalar_one_or_none() is not None:
                    inserted += 1
            return inserted

    async def requeue_stale_contexts(self, *, limit: int = 50) -> int:
        """Reconcile contexts when an older same-event report was ingested later.

        The historical cutoff never moves. We only recompute the context using newly
        available records whose publication/observation time predates that cutoff.
        """
        now = datetime.now(UTC)
        other_article = aliased(ArticleModel)
        other_version = aliased(ArticleVersionModel)
        observed = func.coalesce(other_version.published_at, other_version.retrieved_at)
        async with self._session_factory() as session, session.begin():
            stale_ids = (
                await session.scalars(
                    select(ArticleHistoricalEnrichmentJobModel.id)
                    .join(
                        ArticleHistoricalContextModel,
                        ArticleHistoricalContextModel.article_version_id
                        == ArticleHistoricalEnrichmentJobModel.article_version_id,
                    )
                    .join(
                        other_article,
                        other_article.event_id == ArticleHistoricalContextModel.event_id,
                    )
                    .join(other_version, other_version.article_id == other_article.id)
                    .where(
                        ArticleHistoricalEnrichmentJobModel.state == "succeeded",
                        other_version.id != ArticleHistoricalContextModel.article_version_id,
                        observed < ArticleHistoricalContextModel.cutoff_at,
                        other_version.created_at > ArticleHistoricalContextModel.generated_at,
                    )
                    .distinct()
                    .order_by(ArticleHistoricalEnrichmentJobModel.id)
                    .limit(limit)
                )
            ).all()
            requeued = 0
            for job_id in stale_ids:
                row = await session.get(ArticleHistoricalEnrichmentJobModel, job_id)
                if row is None or row.state != "succeeded":
                    continue
                row.state = "queued"
                row.next_attempt_at = now
                row.refresh_count += 1
                row.last_refresh_reason = "late_prior_same_event_report"
                row.lease_owner = None
                row.lease_expires_at = None
                row.last_error = None
                row.completed_at = None
                row.updated_at = now
                requeued += 1
            return requeued

    async def requeue_missing_semantic_contexts(self, *, limit: int = 50) -> int:
        """Re-enrich older contexts once local semantic retrieval is enabled."""
        if self._semantic_service is None or not self._semantic_service.ready:
            return 0
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.scalars(
                    select(ArticleHistoricalEnrichmentJobModel)
                    .join(
                        ArticleHistoricalContextModel,
                        ArticleHistoricalContextModel.article_version_id
                        == ArticleHistoricalEnrichmentJobModel.article_version_id,
                    )
                    .where(
                        ArticleHistoricalEnrichmentJobModel.state == "succeeded",
                        func.coalesce(
                            ArticleHistoricalContextModel.context_summary[
                                "semantic_search_succeeded"
                            ].astext,
                            "false",
                        )
                        != "true",
                    )
                    .order_by(ArticleHistoricalContextModel.generated_at.desc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                row.state = "queued"
                row.next_attempt_at = now
                row.refresh_count += 1
                row.last_refresh_reason = "semantic_index_enabled"
                row.lease_owner = None
                row.lease_expires_at = None
                row.last_error = None
                row.completed_at = None
                row.updated_at = now
            return len(rows)

    async def lease_due_jobs(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int,
    ) -> tuple[LeasedHistoricalEnrichmentJob, ...]:
        now = datetime.now(UTC)
        lease_expires = now + timedelta(seconds=lease_seconds)
        async with self._session_factory() as session, session.begin():
            rows = (
                await session.scalars(
                    select(ArticleHistoricalEnrichmentJobModel)
                    .where(
                        or_(
                            and_(
                                ArticleHistoricalEnrichmentJobModel.state.in_(["queued", "retry"]),
                                ArticleHistoricalEnrichmentJobModel.next_attempt_at <= now,
                            ),
                            and_(
                                ArticleHistoricalEnrichmentJobModel.state == "running",
                                ArticleHistoricalEnrichmentJobModel.lease_expires_at < now,
                            ),
                        )
                    )
                    .order_by(ArticleHistoricalEnrichmentJobModel.next_attempt_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            leased: list[LeasedHistoricalEnrichmentJob] = []
            for row in rows:
                row.state = "running"
                row.attempt_count += 1
                row.lease_owner = worker_id
                row.lease_expires_at = lease_expires
                row.started_at = now
                row.updated_at = now
                leased.append(
                    LeasedHistoricalEnrichmentJob(
                        id=row.id,
                        article_id=row.article_id,
                        article_version_id=row.article_version_id,
                        event_id=row.event_id,
                        cutoff_at=row.cutoff_at,
                        attempt_count=row.attempt_count,
                        lease_owner=worker_id,
                        lease_started_at=now,
                    )
                )
            return tuple(leased)

    async def heartbeat(self, job: LeasedHistoricalEnrichmentJob, *, lease_seconds: int) -> bool:
        """Renew only an unexpired lease owned by the same historical attempt."""
        if not job.lease_owner or job.lease_started_at is None:
            return False
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(ArticleHistoricalEnrichmentJobModel)
                .where(
                    ArticleHistoricalEnrichmentJobModel.id == job.id,
                    ArticleHistoricalEnrichmentJobModel.state == "running",
                    ArticleHistoricalEnrichmentJobModel.lease_owner == job.lease_owner,
                    ArticleHistoricalEnrichmentJobModel.started_at == job.lease_started_at,
                    ArticleHistoricalEnrichmentJobModel.lease_expires_at > now,
                )
                .values(lease_expires_at=now + timedelta(seconds=max(15, lease_seconds)), updated_at=now)
            )
            return bool(result.rowcount)

    async def process(self, job: LeasedHistoricalEnrichmentJob) -> None:
        try:
            payload = await self._build_context(job)
            await self._persist_success(job, payload)
        except Exception as exc:
            await self._persist_failure(job, exc)
            raise

    async def _build_context(self, job: LeasedHistoricalEnrichmentJob) -> dict[str, Any]:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, job.article_id)
            version = await session.get(ArticleVersionModel, job.article_version_id)
            if article is None or version is None:
                raise RuntimeError("historical enrichment target article/version no longer exists")
            claims = list(
                (
                    await session.scalars(
                        select(ArticleClaimModel)
                        .where(ArticleClaimModel.article_version_id == version.id)
                        .order_by(ArticleClaimModel.sentence_index)
                    )
                ).all()
            )
            queries = build_historical_queries(
                title=version.title,
                claim_features=[claim.extraction_features for claim in claims],
                max_queries=self._max_queries,
            )
            same_event = await self._same_event_history(session, job)
            prior_claims = await self._prior_claim_history(session, job, claims)
            current_entities = _claim_entities(claims)
            current_terms = _salient_terms(
                " ".join([version.title, *[claim.claim_text for claim in claims[:10]]])
            )
            internal_matches = await self._internal_matches(
                session,
                job=job,
                title=version.title,
                claims=claims,
                current_entities=current_entities,
            )
            semantic_query_text = " ".join(
                [version.title, *[claim.claim_text for claim in claims[:10]]]
            )[:12_000]

        semantic_matches: list[dict[str, object]] = []
        semantic_status: dict[str, object] | None = None
        if self._semantic_service is not None and semantic_query_text.strip():
            try:
                raw_semantic = await self._semantic_service.search(
                    text=semantic_query_text,
                    cutoff_at=job.cutoff_at,
                    exclude_version_id=job.article_version_id,
                    limit=self._semantic_limit,
                )
                semantic_matches = _score_semantic_matches(
                    raw_semantic,
                    current_entities=current_entities,
                    current_terms=current_terms,
                )
                semantic_status = {
                    "provider": "local_semantic_qdrant",
                    "success": True,
                    "result_count": len(semantic_matches),
                }
            except Exception as exc:
                logger.warning(
                    "historical_semantic_search_failed",
                    article_version_id=str(job.article_version_id),
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:300],
                )
                semantic_status = {
                    "provider": "local_semantic_qdrant",
                    "success": False,
                    "result_count": 0,
                    "error_type": type(exc).__name__,
                }

        if semantic_matches:
            internal_matches.extend(semantic_matches)

        external_matches: list[dict[str, object]] = []
        provider_statuses: list[dict[str, object]] = []
        if self._external_enabled and queries:
            external_matches, provider_statuses = await self._external_matches(
                queries=queries,
                cutoff_at=job.cutoff_at,
                current_url=version.final_url,
                current_terms=current_terms,
                current_entities=current_entities,
            )
        if semantic_status is not None:
            provider_statuses.append(semantic_status)

        same_event, internal_matches, external_matches, duplicate_history_count = (
            _deduplicate_article_channels(
                same_event=same_event,
                internal_matches=internal_matches,
                external_matches=external_matches,
            )
        )

        times: list[datetime] = []
        for item in (*same_event, *prior_claims, *internal_matches, *external_matches):
            raw = item.get("published_at") or item.get("retrieved_at") or item.get("observed_at")
            parsed = _parse_datetime(raw)
            if parsed is not None:
                times.append(parsed)

        summary = timeline_summary(times, cutoff_at=job.cutoff_at)
        depth = historical_depth(
            same_event_count=len(same_event),
            prior_claim_count=len(prior_claims),
            internal_match_count=len(internal_matches),
            external_match_count=len(external_matches),
        )
        status = "complete" if self._external_enabled else "internal_only"
        if self._external_enabled and provider_statuses and not any(
            bool(item.get("success")) for item in provider_statuses
        ):
            status = "partial"

        current_by_family = {
            str(claim.extraction_features.get("claim_family_key")): claim
            for claim in claims
            if claim.extraction_features.get("claim_family_key")
        }
        prior_by_family: dict[str, list[dict[str, object]]] = {}
        for item in prior_claims:
            family = str(item.get("claim_family_key") or "")
            if family:
                prior_by_family.setdefault(family, []).append(item)
        recurring_families = set(current_by_family) & set(prior_by_family)
        new_families = set(current_by_family) - set(prior_by_family)
        numeric_changes = 0
        temporal_changes = 0
        changed_families = 0
        revision_candidate_count = 0
        claim_evolution: list[dict[str, object]] = []
        for family in sorted(recurring_families):
            current = current_by_family[family]
            prior = prior_by_family[family][0]
            current_quantities = current.extraction_features.get("quantities", [])
            current_temporal = current.extraction_features.get("temporal_references", [])
            prior_quantities = prior.get("quantities", [])
            prior_temporal = prior.get("temporal_references", [])
            numeric_changed = (
                bool(current_quantities or prior_quantities)
                and current_quantities != prior_quantities
            )
            temporal_changed = (
                bool(current_temporal or prior_temporal)
                and current_temporal != prior_temporal
            )
            text_changed = " ".join(current.claim_text.casefold().split()) != " ".join(
                str(prior.get("claim_text") or "").casefold().split()
            )
            same_temporal_reference = bool(current_temporal or prior_temporal) and (
                current_temporal == prior_temporal
            )
            evolution_type = classify_claim_evolution(
                numeric_changed=numeric_changed,
                temporal_changed=temporal_changed,
                text_changed=text_changed,
                same_temporal_reference=same_temporal_reference,
            )
            if evolution_type == "numeric_revision_candidate":
                revision_candidate_count += 1
            if numeric_changed:
                numeric_changes += 1
            if temporal_changed:
                temporal_changes += 1
            if text_changed or numeric_changed or temporal_changed:
                changed_families += 1
            claim_evolution.append(
                {
                    "claim_family_key": family,
                    "current_claim_id": str(current.id),
                    "current_claim_text": current.claim_text,
                    "prior_claim_id": prior.get("claim_id"),
                    "prior_claim_text": prior.get("claim_text"),
                    "numeric_change": numeric_changed,
                    "temporal_change": temporal_changed,
                    "text_change": text_changed,
                    "evolution_type": evolution_type,
                    "same_temporal_reference": same_temporal_reference,
                    "prior_source_url": prior.get("source_url"),
                    "prior_published_at": prior.get("published_at"),
                    "prior_verification_label": prior.get("verification_label"),
                }
            )

        change_pattern = summarize_change_pattern(
            current_claim_count=len(current_by_family),
            new_claim_count=len(new_families),
            recurring_claim_count=len(recurring_families),
            changed_claim_count=changed_families,
            revision_candidate_count=revision_candidate_count,
        )
        article_matches = [*same_event, *internal_matches, *external_matches]
        relevance_scores = [
            float(item.get("relevance_score") or 0.0)
            for item in [*article_matches, *prior_claims]
        ]
        source_keys = {
            key
            for item in article_matches
            if (key := _history_source_key(item)) is not None
        }
        channel_count = sum(
            bool(values)
            for values in (same_event, prior_claims, internal_matches, external_matches)
        )
        context_confidence = historical_context_confidence(
            relevance_scores=relevance_scores,
            source_diversity_count=len(source_keys),
            channel_count=channel_count,
            duplicate_count=duplicate_history_count,
        )
        top_matches = sorted(
            article_matches,
            key=lambda item: float(item.get("relevance_score") or 0.0),
            reverse=True,
        )[:8]

        return {
            "status": status,
            "queries": list(queries),
            "same_event_history": same_event,
            "prior_claim_history": prior_claims,
            "internal_matches": internal_matches,
            "external_matches": external_matches,
            "provider_statuses": provider_statuses,
            "timeline_summary": summary,
            "dependency_sources": _historical_dependency_sources(
                job=job,
                claims=claims,
                same_event=same_event,
                prior_claims=prior_claims,
                internal_matches=internal_matches,
            ),
            "context_summary": {
                "historical_context_available": depth != "none",
                "historical_depth": depth,
                "same_event_article_count": len(same_event),
                "prior_claim_family_match_count": len(prior_claims),
                "internal_match_count": len(internal_matches),
                "semantic_match_count": sum(
                    1
                    for item in internal_matches
                    if item.get("retrieval_channel") == "qdrant_local_embedding"
                ),
                "semantic_search_enabled": self._semantic_service is not None,
                "semantic_search_succeeded": bool(
                    semantic_status is not None and semantic_status.get("success") is True
                ),
                "external_match_count": len(external_matches),
                "external_search_enabled": self._external_enabled,
                "current_claim_family_count": len(current_by_family),
                "new_claim_family_count": len(new_families),
                "recurring_claim_family_count": len(recurring_families),
                "changed_claim_family_count": changed_families,
                "numeric_change_family_count": numeric_changes,
                "temporal_change_family_count": temporal_changes,
                "revision_candidate_family_count": revision_candidate_count,
                "change_pattern": change_pattern,
                "claim_evolution": claim_evolution[:25],
                "historical_context_confidence": context_confidence,
                "historical_confidence_scope": (
                    "Confidence estimates linkage/coverage of historical context, not factual truth."
                ),
                "source_diversity_count": len(source_keys),
                "historical_channel_count": channel_count,
                "duplicate_history_item_count": duplicate_history_count,
                "high_relevance_match_count": sum(
                    1 for value in relevance_scores if value >= 0.75
                ),
                "top_historical_matches": top_matches,
                "what_changed": {
                    "pattern": change_pattern,
                    "new_claim_families": len(new_families),
                    "recurring_claim_families": len(recurring_families),
                    "changed_claim_families": changed_families,
                    "numeric_changes": numeric_changes,
                    "temporal_changes": temporal_changes,
                    "revision_candidates": revision_candidate_count,
                },
                "cutoff_at": job.cutoff_at.isoformat(),
                "time_semantics": (
                    "Only evidence observed/published before the article enrichment "
                    "cutoff is included automatically."
                ),
            },
        }

    async def _same_event_history(
        self,
        session: AsyncSession,
        job: LeasedHistoricalEnrichmentJob,
    ) -> list[dict[str, object]]:
        observed = func.coalesce(ArticleVersionModel.published_at, ArticleVersionModel.retrieved_at)
        rows = (
            await session.execute(
                select(ArticleVersionModel, ArticleModel, PublisherModel)
                .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                .join(PublisherModel, PublisherModel.id == ArticleModel.publisher_id)
                .where(
                    ArticleModel.event_id == job.event_id,
                    ArticleVersionModel.id != job.article_version_id,
                    observed < job.cutoff_at,
                )
                .order_by(observed.desc())
                .limit(self._internal_limit)
            )
        ).all()
        return [
            {
                "article_id": str(article.id),
                "article_version_id": str(version.id),
                "publisher": publisher.name,
                "title": version.title,
                "url": version.final_url,
                "published_at": _iso(version.published_at),
                "retrieved_at": _iso(version.retrieved_at),
                "relationship": (
                    "same_article_prior_version"
                    if article.id == job.article_id
                    else "same_event_prior_reporting"
                ),
                **_relevance_fields(
                    historical_relevance_score(
                        same_event=True,
                        source_signal=1.0 if article.id == job.article_id else 0.9,
                    )
                ),
            }
            for version, article, publisher in rows
        ]

    async def _prior_claim_history(
        self,
        session: AsyncSession,
        job: LeasedHistoricalEnrichmentJob,
        current_claims: list[ArticleClaimModel],
    ) -> list[dict[str, object]]:
        families = {
            str(value)
            for claim in current_claims
            if (value := claim.extraction_features.get("claim_family_key"))
        }
        if not families:
            return []
        family_key = ArticleClaimModel.extraction_features["claim_family_key"].astext
        rows = (
            await session.execute(
                select(ArticleClaimModel, ArticleVersionModel, ArticleModel)
                .join(
                    ArticleVersionModel,
                    ArticleVersionModel.id == ArticleClaimModel.article_version_id,
                )
                .join(ArticleModel, ArticleModel.id == ArticleClaimModel.article_id)
                .where(
                    ArticleVersionModel.id != job.article_version_id,
                    family_key.in_(families),
                    func.coalesce(
                        ArticleVersionModel.published_at,
                        ArticleVersionModel.retrieved_at,
                    )
                    < job.cutoff_at,
                )
                .order_by(desc(ArticleVersionModel.retrieved_at))
                .limit(max(self._internal_limit * 4, self._internal_limit))
            )
        ).all()
        claim_ids = [claim.id for claim, _version, _article in rows]
        latest_verifications: dict[UUID, ClaimVerificationModel] = {}
        if claim_ids:
            verification_rows = (
                await session.scalars(
                    select(ClaimVerificationModel)
                    .where(ClaimVerificationModel.claim_id.in_(claim_ids))
                    .order_by(
                        ClaimVerificationModel.claim_id,
                        ClaimVerificationModel.created_at.desc(),
                    )
                )
            ).all()
            for verification in verification_rows:
                latest_verifications.setdefault(verification.claim_id, verification)

        matches: list[dict[str, object]] = []
        for claim, version, article in rows:
            family = str(claim.extraction_features.get("claim_family_key") or "")
            verification = latest_verifications.get(claim.id)
            matches.append(
                {
                    "claim_id": str(claim.id),
                    "article_id": str(article.id),
                    "article_version_id": str(version.id),
                    "claim_family_key": family,
                    "claim_text": claim.claim_text,
                    "claim_type": claim.extraction_features.get("claim_type"),
                    "quantities": claim.extraction_features.get("quantities", []),
                    "temporal_references": claim.extraction_features.get("temporal_references", []),
                    "verification_label": verification.label if verification else None,
                    "verification_confidence": (
                        verification.confidence_score if verification else None
                    ),
                    "published_at": _iso(version.published_at),
                    "retrieved_at": _iso(version.retrieved_at),
                    "source_url": version.final_url,
                    **_relevance_fields(
                        historical_relevance_score(
                            claim_family_match=True,
                            source_signal=0.85,
                        )
                    ),
                }
            )
            if len(matches) >= self._internal_limit:
                break
        return matches

    async def _internal_matches(
        self,
        session: AsyncSession,
        *,
        job: LeasedHistoricalEnrichmentJob,
        title: str,
        claims: list[ArticleClaimModel],
        current_entities: set[str],
    ) -> list[dict[str, object]]:
        observed = func.coalesce(ArticleVersionModel.published_at, ArticleVersionModel.retrieved_at)
        current_terms = _salient_terms(
            " ".join([title, *[claim.claim_text for claim in claims[:10]]])
        )
        if not current_terms:
            return []

        # Full-corpus retrieval: PostgreSQL first narrows/ranks candidates using a
        # GIN-backed tsvector expression (migration 0020). We then retain the
        # explainable entity/lexical scorer as a second-stage reranker.
        query_text = " OR ".join(sorted(current_terms)[:12])
        search_query = func.websearch_to_tsquery("simple", query_text)
        document = func.to_tsvector(
            "simple",
            func.coalesce(ArticleVersionModel.title, "")
            + " "
            + func.coalesce(ArticleVersionModel.text_content, ""),
        )
        rank = func.ts_rank_cd(document, search_query).label("fts_rank")
        rows = (
            await session.execute(
                select(ArticleVersionModel, ArticleModel, PublisherModel, rank)
                .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                .join(PublisherModel, PublisherModel.id == ArticleModel.publisher_id)
                .where(
                    ArticleVersionModel.id != job.article_version_id,
                    observed < job.cutoff_at,
                    document.op("@@")(search_query),
                )
                .order_by(rank.desc(), observed.desc())
                .limit(max(self._internal_limit * 8, 100))
            )
        ).all()
        scored: list[tuple[float, ArticleVersionModel, ArticleModel, PublisherModel, dict[str, object], float, float, float]] = []
        for version, article, publisher, fts_rank in rows:
            candidate_terms = _salient_terms(f"{version.title} {version.text_content[:3000]}")
            if not current_terms or not candidate_terms:
                continue
            overlap = len(current_terms & candidate_terms)
            lexical_score = overlap / max(1, len(current_terms))
            if lexical_score < 0.12:
                continue
            entity_score = _entity_overlap(current_entities, f"{version.title} {version.text_content[:3000]}")
            relevance = historical_relevance_score(
                entity_overlap=entity_score,
                lexical_overlap=lexical_score,
                source_signal=0.65,
            )
            scored.append((
                float(relevance["score"]),
                version,
                article,
                publisher,
                relevance,
                lexical_score,
                entity_score,
                float(fts_rank or 0.0),
            ))
        scored.sort(key=lambda item: (item[0], item[1].retrieved_at), reverse=True)
        return [
            {
                "article_id": str(article.id),
                "event_id": str(article.event_id),
                "article_version_id": str(version.id),
                "publisher": publisher.name,
                "title": version.title,
                "url": version.final_url,
                "published_at": _iso(version.published_at),
                "retrieved_at": _iso(version.retrieved_at),
                "similarity_score": round(lexical_score, 6),
                "fts_rank": round(fts_rank, 6),
                "entity_overlap": round(entity_score, 6),
                "relationship": "full_corpus_related_prior_reporting",
                **_relevance_fields(relevance),
            }
            for score, version, article, publisher, relevance, lexical_score, entity_score, fts_rank
            in scored[: self._internal_limit]
        ]

    async def _external_matches(
        self,
        *,
        queries: tuple[str, ...],
        cutoff_at: datetime,
        current_url: str,
        current_terms: set[str],
        current_entities: set[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        assert self._external_service is not None
        seen_urls: set[str] = {current_url}
        matches: list[dict[str, object]] = []
        statuses: list[dict[str, object]] = []
        for query in queries:
            response = await self._external_service.search(
                HistoricalSearchCommand(
                    query=query,
                    to_date=cutoff_at.date(),
                    limit=self._external_limit_per_query,
                )
            )
            for status in response.provider_statuses:
                statuses.append(
                    {
                        "query": query,
                        "provider": status.provider.value,
                        "configured": status.configured,
                        "success": status.success,
                        "result_count": status.result_count,
                        "error_code": status.error_code,
                        "message": status.message,
                    }
                )
            for item in response.results:
                if item.url in seen_urls:
                    continue
                published_at = item.published_at
                if published_at is None:
                    # Unknown publication time cannot safely be asserted as historical.
                    continue
                if published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=UTC)
                if published_at >= cutoff_at:
                    continue
                seen_urls.add(item.url)
                candidate_text = f"{item.title} {item.snippet or ''}"
                candidate_terms = _salient_terms(candidate_text)
                lexical_score = _term_overlap(current_terms, candidate_terms)
                entity_score = _entity_overlap(current_entities, candidate_text)
                relevance = historical_relevance_score(
                    entity_overlap=entity_score,
                    lexical_overlap=lexical_score,
                    source_signal=0.55,
                )
                matches.append(
                    {
                        "query": query,
                        "provider": item.provider.value,
                        "result_type": item.result_type.value,
                        "title": item.title,
                        "url": item.url,
                        "source_name": item.source_name,
                        "published_at": _iso(published_at),
                        "snippet": item.snippet,
                        "metadata": item.metadata,
                        "similarity_score": round(lexical_score, 6),
                        "entity_overlap": round(entity_score, 6),
                        **_relevance_fields(relevance),
                    }
                )
        return matches[: self._internal_limit * 2], statuses

    async def _persist_success(
        self,
        job: LeasedHistoricalEnrichmentJob,
        payload: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            leased = await session.get(ArticleHistoricalEnrichmentJobModel, job.id, with_for_update=True)
            if not _owns_historical_lease(leased, job, now):
                logger.warning("historical_enrichment_stale_result_discarded", job_id=str(job.id))
                return
            values = {
                "article_id": job.article_id,
                "article_version_id": job.article_version_id,
                "event_id": job.event_id,
                "methodology_version": HISTORICAL_ENRICHMENT_VERSION,
                "status": payload["status"],
                "cutoff_at": job.cutoff_at,
                "queries": payload["queries"],
                "same_event_history": payload["same_event_history"],
                "prior_claim_history": payload["prior_claim_history"],
                "internal_matches": payload["internal_matches"],
                "external_matches": payload["external_matches"],
                "provider_statuses": payload["provider_statuses"],
                "timeline_summary": payload["timeline_summary"],
                "context_summary": payload["context_summary"],
                "generated_at": now,
                "updated_at": now,
            }
            statement = insert(ArticleHistoricalContextModel).values(
                id=uuid7(),
                created_at=now,
                **values,
            )
            context_id = (
                await session.execute(
                    statement.on_conflict_do_update(
                        constraint="uq_article_historical_context_version",
                        set_={key: getattr(statement.excluded, key) for key in values},
                    ).returning(ArticleHistoricalContextModel.id)
                )
            ).scalar_one()
            dependency_sources = tuple(
                DependencySource(kind=str(item["kind"]), id=UUID(str(item["id"])))
                for item in payload.get("dependency_sources", [])
                if isinstance(item, dict) and item.get("kind") and item.get("id")
            )
            await self._dependencies.replace_dependencies(
                artifact_kind=HISTORICAL_CONTEXT_ARTIFACT,
                artifact_id=context_id,
                sources=dependency_sources,
                session=session,
            )
            await self._dependencies.mark_fresh(
                artifact_kind=HISTORICAL_CONTEXT_ARTIFACT,
                artifact_id=context_id,
                session=session,
            )
            briefing_stmt = insert(EventBriefingJobModel).values(
                id=uuid7(), event_id=job.event_id, trigger_article_version_id=job.article_version_id,
                state="queued", attempt_count=0, next_attempt_at=now, created_at=now, updated_at=now,
            )
            await session.execute(
                briefing_stmt.on_conflict_do_update(
                    constraint="uq_event_briefing_job_event",
                    set_={
                        "trigger_article_version_id": job.article_version_id,
                        "state": "queued", "next_attempt_at": now, "last_error": None,
                        "completed_at": None, "updated_at": now,
                    },
                    where=(EventBriefingJobModel.state != "running") | (EventBriefingJobModel.lease_expires_at < now),
                )
            )
            row = leased
            if row is not None:
                row.state = "succeeded"
                row.completed_at = now
                if row.refresh_count > 0:
                    row.last_reconciled_at = now
                row.lease_owner = None
                row.lease_expires_at = None
                row.last_error = None
                row.updated_at = now
        logger.info(
            "historical_enrichment_completed",
            article_id=str(job.article_id),
            article_version_id=str(job.article_version_id),
            status=payload["status"],
            internal_matches=len(payload["internal_matches"]),
            external_matches=len(payload["external_matches"]),
        )

    async def _persist_failure(self, job: LeasedHistoricalEnrichmentJob, exc: Exception) -> None:
        now = datetime.now(UTC)
        retry = job.attempt_count < self._max_attempts
        async with self._session_factory() as session, session.begin():
            row = await session.get(ArticleHistoricalEnrichmentJobModel, job.id, with_for_update=True)
            if not _owns_historical_lease(row, job, now):
                logger.warning("historical_enrichment_stale_failure_discarded", job_id=str(job.id))
                return
            row.state = "retry" if retry else "failed"
            row.next_attempt_at = now + timedelta(
                seconds=min(3600, 60 * (2 ** max(0, job.attempt_count - 1)))
            )
            row.lease_owner = None
            row.lease_expires_at = None
            row.last_error = f"{type(exc).__name__}: {str(exc)[:1800]}"
            row.updated_at = now
            if not retry:
                row.completed_at = now
        logger.exception(
            "historical_enrichment_failed",
            article_id=str(job.article_id),
            article_version_id=str(job.article_version_id),
            attempt_count=job.attempt_count,
            retry=retry,
            error_type=type(exc).__name__,
        )


def _owns_historical_lease(row: ArticleHistoricalEnrichmentJobModel | None, job: LeasedHistoricalEnrichmentJob, now: datetime) -> bool:
    """A stale worker must not write any context, dependency, or retry state."""
    if row is None or row.state != "running":
        return False
    if job.lease_owner is None or job.lease_started_at is None:
        return False
    return bool(
        row.lease_owner == job.lease_owner
        and row.started_at == job.lease_started_at
        and row.lease_expires_at is not None
        and row.lease_expires_at > now
    )


def _relevance_fields(result: dict[str, object]) -> dict[str, object]:
    return {
        "relevance_score": float(result.get("score") or 0.0),
        "relevance_label": str(result.get("label") or "weak"),
        "relevance_scope": str(
            result.get("scope") or "historical_linkage_not_factual_truth"
        ),
        "relevance_signals": dict(result.get("signals") or {}),
    }


def _claim_entities(claims: list[ArticleClaimModel]) -> set[str]:
    values: set[str] = set()
    for claim in claims:
        raw = claim.extraction_features.get("entities")
        if not isinstance(raw, list):
            continue
        for value in raw:
            normalized = " ".join(str(value).casefold().split()).strip(" ,.;:")
            if len(normalized) >= 3:
                values.add(normalized)
    return values


def _term_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left))


def _entity_overlap(current_entities: set[str], candidate_text: str) -> float:
    if not current_entities:
        return 0.0
    haystack = " ".join(candidate_text.casefold().split())
    matched = sum(1 for entity in current_entities if entity in haystack)
    return matched / max(1, len(current_entities))


def _history_source_key(item: dict[str, object]) -> str | None:
    for key in ("publisher", "source_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return f"name:{value.casefold().strip()}"
    normalized = normalize_history_url(item.get("url") or item.get("source_url"))
    if normalized and "://" in normalized:
        return "domain:" + normalized.split("://", 1)[1].split("/", 1)[0]
    provider = item.get("provider")
    if isinstance(provider, str) and provider:
        return f"provider:{provider.casefold()}"
    return None


def _score_semantic_matches(
    items: list[dict[str, object]],
    *,
    current_entities: set[str],
    current_terms: set[str],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for item in items:
        title = str(item.get("title") or "")
        semantic = max(0.0, min(1.0, float(item.get("semantic_similarity") or 0.0)))
        candidate_terms = _salient_terms(title)
        lexical = _term_overlap(current_terms, candidate_terms)
        entity = _entity_overlap(current_entities, title)
        score = min(1.0, 0.55 * semantic + 0.20 * entity + 0.15 * lexical + 0.05)
        enriched = dict(item)
        enriched.update(
            {
                "relevance_score": round(score, 6),
                "relevance_label": (
                    "high"
                    if score >= 0.75
                    else "moderate"
                    if score >= 0.45
                    else "limited"
                    if score >= 0.20
                    else "weak"
                ),
                "relevance_scope": "historical_linkage_not_factual_truth",
                "relevance_signals": {
                    "semantic_similarity": round(semantic, 6),
                    "entity_overlap": round(entity, 6),
                    "lexical_overlap": round(lexical, 6),
                },
            }
        )
        output.append(enriched)
    return output


def _deduplicate_article_channels(
    *,
    same_event: list[dict[str, object]],
    internal_matches: list[dict[str, object]],
    external_matches: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    int,
]:
    combined: list[dict[str, object]] = []
    for channel, values in (
        ("same_event", same_event),
        ("internal", internal_matches),
        ("external", external_matches),
    ):
        for value in values:
            combined.append({**value, "historical_channel": channel})
    unique, dropped = deduplicate_history_items(combined)
    result: dict[str, list[dict[str, object]]] = {
        "same_event": [],
        "internal": [],
        "external": [],
    }
    for item in unique:
        channel = str(item.get("historical_channel") or "")
        if channel in result:
            result[channel].append(item)
    return result["same_event"], result["internal"], result["external"], dropped


def _salient_terms(text: str) -> set[str]:
    stop = {
        "that", "with", "from", "this", "have", "will", "said", "after",
        "before", "their", "about", "into", "over", "under", "report", "news",
        "और", "का", "की", "के", "को", "में", "से", "पर", "है", "हैं", "ने",
    }
    values: set[str] = set()
    buffer: list[str] = []
    for char in text.casefold():
        category = unicodedata.category(char)
        if category[:1] in {"L", "N", "M"} or char in {".", "'", "’", "_", "-"}:
            buffer.append(char)
            continue
        if buffer:
            token = "".join(buffer).strip(".'’_-")
            if len(token) >= 3 and token not in stop:
                values.add(token)
            buffer.clear()
    if buffer:
        token = "".join(buffer).strip(".'’_-")
        if len(token) >= 3 and token not in stop:
            values.add(token)
    return values


def _historical_dependency_sources(
    *,
    job: LeasedHistoricalEnrichmentJob,
    claims: list[ArticleClaimModel],
    same_event: list[dict[str, object]],
    prior_claims: list[dict[str, object]],
    internal_matches: list[dict[str, object]],
) -> list[dict[str, str]]:
    sources: set[tuple[str, UUID]] = {
        ("article_version", job.article_version_id),
        ("article", job.article_id),
        ("event", job.event_id),
    }
    sources.update(("claim", claim.id) for claim in claims)
    for item in (*same_event, *prior_claims, *internal_matches):
        for kind, key in (
            ("article", "article_id"),
            ("article_version", "article_version_id"),
            ("claim", "claim_id"),
            ("event", "event_id"),
        ):
            raw = item.get(key)
            if raw:
                try:
                    sources.add((kind, UUID(str(raw))))
                except (ValueError, TypeError):
                    continue
    return [
        {"kind": kind, "id": str(source_id)}
        for kind, source_id in sorted(sources, key=lambda item: (item[0], str(item[1])))
    ]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
