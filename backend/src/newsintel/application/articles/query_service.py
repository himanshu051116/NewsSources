from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.articles.dto import (
    ArticleClaimHistoryView,
    ArticleClaimView,
    ArticleDetailView,
    ArticleHistoricalContextView,
    ArticleIntelligenceStateView,
    ArticleQualityProfileView,
    ArticleSummaryView,
    HistoricalEnrichmentStateView,
    ArticleVersionChangeView,
    ArticleVersionDiffView,
    ArticleVersionHistoryEntryView,
    ArticleVersionHistoryView,
    ArticleVersionView,
    ClaimEvidenceLinkView,
    ClaimEvidenceSearchRunSummaryView,
    ClaimConflictSummaryView,
    ClaimInvestigationView,
    ClaimReviewFlagSummaryView,
    EvidenceLineageSummaryView,
    ClaimHistoryFamilyView,
    ClaimHistoryRevisionView,
    ClaimVerificationSnapshotView,
    ClaimVerificationView,
    EventDetailView,
    EventDossierClaimView,
    EventDossierView,
    EventPublisherBreakdownView,
    EventSummaryView,
    IntelligenceSearchView,
    EventTimelinePointView,
    EventTimelineView,
    QualityDimensionView,
)
from newsintel.domain.intelligence.quality import (
    ArticleQualitySignals,
    ClaimQualitySignal,
    assess_article_quality,
    evidence_domain,
)
from newsintel.domain.intelligence.versioning import VersionDiff, diff_article_versions
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleHistoricalContextModel,
    ArticleHistoricalEnrichmentJobModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimEvidenceLinkModel,
    ClaimVerificationModel,
    ClaimConflictResolutionModel,
    ClaimReviewFlagModel,
    DerivedArtifactStateModel,
    EventModel,
    EvidenceSearchRunModel,
    PublisherModel,
    PublisherReliabilitySnapshotModel,
)


class ArticleQueryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_articles(
        self, *, limit: int = 50, offset: int = 0,
        before_observed_at: datetime | None = None, before_id: UUID | None = None,
    ) -> list[ArticleSummaryView]:
        """Stable newest-first article pages, with an optional keyset continuation.

        Legacy offset pagination remains supported for callers that still use it.
        Keyset pages use the observation timestamp plus UUID as a total ordering,
        preventing new arrivals from shifting the older-story continuation.
        """
        if (before_observed_at is None) != (before_id is None):
            raise ValueError('before_observed_at and before_id must be supplied together')
        if before_observed_at is not None and before_observed_at.tzinfo is None:
            raise ValueError('before_observed_at must include an explicit timezone')
        if before_id is not None and offset:
            raise ValueError('cursor continuation cannot be mixed with offset')
        statement = select(ArticleModel).order_by(
            desc(ArticleModel.first_observed_at), desc(ArticleModel.id)
        )
        if before_observed_at is not None and before_id is not None:
            statement = statement.where(or_(
                ArticleModel.first_observed_at < before_observed_at,
                and_(ArticleModel.first_observed_at == before_observed_at, ArticleModel.id < before_id),
            ))
        elif offset:
            statement = statement.offset(offset)
        async with self._session_factory() as session:
            articles = list((await session.scalars(statement.limit(limit))).all())
            if not articles:
                return []
            article_ids = [article.id for article in articles]
            versions = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.article_id.in_(article_ids))
                        .order_by(
                            ArticleVersionModel.article_id,
                            desc(ArticleVersionModel.version_number),
                        )
                    )
                ).all()
            )
            latest_by_article: dict[UUID, ArticleVersionModel] = {}
            for version in versions:
                latest_by_article.setdefault(version.article_id, version)
            version_ids = [version.id for version in latest_by_article.values()]
            contexts = list(
                (
                    await session.scalars(
                        select(ArticleHistoricalContextModel).where(
                            ArticleHistoricalContextModel.article_version_id.in_(version_ids)
                        )
                    )
                ).all()
            ) if version_ids else []
            jobs = list(
                (
                    await session.scalars(
                        select(ArticleHistoricalEnrichmentJobModel).where(
                            ArticleHistoricalEnrichmentJobModel.article_version_id.in_(version_ids)
                        )
                    )
                ).all()
            ) if version_ids else []
            context_by_version = {row.article_version_id: row for row in contexts}
            job_by_version = {row.article_version_id: row for row in jobs}
            return [
                _summary_from_models(
                    article,
                    latest_by_article.get(article.id),
                    context_by_version.get(latest_by_article[article.id].id)
                    if article.id in latest_by_article
                    else None,
                    job_by_version.get(latest_by_article[article.id].id)
                    if article.id in latest_by_article
                    else None,
                )
                for article in articles
            ]

    async def get_article(self, article_id: UUID) -> ArticleDetailView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            latest = await self._latest_version(session, article.id)
            historical_context = (
                await self._historical_context_for_version(session, latest.id)
                if latest is not None
                else None
            )
            historical_job = (
                await self._historical_job_for_version(session, latest.id)
                if latest is not None
                else None
            )
            return ArticleDetailView(
                id=article.id,
                event_id=article.event_id,
                publisher_id=article.publisher_id,
                canonical_url=article.canonical_url,
                title=article.title,
                language=article.language,
                published_at=article.published_at,
                first_observed_at=article.first_observed_at,
                created_at=article.created_at,
                updated_at=article.updated_at,
                latest_version=_version_view(latest) if latest else None,
                historical_context=(
                    _historical_context_view(historical_context)
                    if historical_context is not None
                    else None
                ),
                historical_enrichment=(
                    _historical_job_view(historical_job)
                    if historical_job is not None
                    else None
                ),
            )

    async def get_article_intelligence_state(
        self,
        article_id: UUID,
    ) -> ArticleIntelligenceStateView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            latest = await self._latest_version(session, article.id)
            if latest is None:
                return ArticleIntelligenceStateView(
                    article_id=article.id,
                    state="discovered",
                    updated_at=article.updated_at,
                )
            context = await self._historical_context_for_version(session, latest.id)
            job = await self._historical_job_for_version(session, latest.id)
            claim_ids = list(
                (
                    await session.scalars(
                        select(ArticleClaimModel.id).where(
                            ArticleClaimModel.article_version_id == latest.id
                        )
                    )
                ).all()
            )
            review_required = 0
            critical_reviews = 0
            if claim_ids:
                flags = list(
                    (
                        await session.scalars(
                            select(ClaimReviewFlagModel).where(
                                ClaimReviewFlagModel.claim_id.in_(claim_ids),
                                ClaimReviewFlagModel.resolved_at.is_(None),
                            )
                        )
                    ).all()
                )
                review_required = len({flag.claim_id for flag in flags})
                critical_reviews = len(
                    {flag.claim_id for flag in flags if flag.severity == "critical"}
                )

            derived_stale = False
            if context is not None:
                derived_state = await session.scalar(
                    select(DerivedArtifactStateModel).where(
                        DerivedArtifactStateModel.artifact_kind == "historical_context",
                        DerivedArtifactStateModel.artifact_id == context.id,
                    )
                )
                derived_stale = bool(derived_state is not None and derived_state.stale)
            history_state = (
                "stale_recompute_pending"
                if derived_stale
                else (context.status if context is not None else (job.state if job else None))
            )
            summary = dict(context.context_summary) if context is not None else {}
            depth = summary.get("historical_depth")
            pattern = summary.get("change_pattern")
            if review_required:
                state = "review_required"
            elif derived_stale:
                state = "enriching"
            elif context is not None:
                state = "ready_with_warnings" if latest.extraction_warnings else "ready"
            elif job is not None and job.state in {"queued", "running"}:
                state = "enriching"
            elif job is not None and job.state == "failed":
                state = "ready_with_warnings"
            else:
                state = "extracted"
            updated_at = max(
                article.updated_at,
                context.updated_at if context is not None else article.updated_at,
                job.updated_at if job is not None else article.updated_at,
            )
            return ArticleIntelligenceStateView(
                article_id=article.id,
                state=state,
                historical_state=history_state,
                historical_depth=depth if isinstance(depth, str) else None,
                historical_change_pattern=pattern if isinstance(pattern, str) else None,
                extraction_warning_count=len(latest.extraction_warnings),
                review_required_claim_count=review_required,
                critical_review_claim_count=critical_reviews,
                updated_at=updated_at,
            )

    async def get_article_historical_context(
        self,
        article_id: UUID,
    ) -> ArticleHistoricalContextView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            latest = await self._latest_version(session, article.id)
            if latest is None:
                return None
            context = await self._historical_context_for_version(session, latest.id)
            return _historical_context_view(context) if context is not None else None

    async def list_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        query: str | None = None,
        lifecycle_status: str | None = None,
    ) -> list[EventSummaryView]:
        async with self._session_factory() as session:
            statement = (
                select(
                    EventModel,
                    func.count(ArticleModel.id).label("article_count"),
                    func.count(func.distinct(ArticleModel.publisher_id)).label("publisher_count"),
                )
                .outerjoin(ArticleModel, ArticleModel.event_id == EventModel.id)
                .group_by(EventModel.id)
                .order_by(desc(EventModel.last_material_change_at), desc(EventModel.first_detected_at))
            )
            normalized_query = (query or "").strip()
            if normalized_query:
                statement = statement.where(EventModel.title.ilike(f"%{normalized_query}%"))
            if lifecycle_status:
                statement = statement.where(EventModel.lifecycle_status == lifecycle_status)
            rows = (await session.execute(statement.offset(offset).limit(limit))).all()
            return [
                EventSummaryView(
                    id=event.id,
                    slug=event.slug,
                    title=event.title,
                    lifecycle_status=event.lifecycle_status,
                    assignment_status=event.assignment_status,
                    first_detected_at=event.first_detected_at,
                    last_material_change_at=event.last_material_change_at,
                    article_count=int(article_count or 0),
                    publisher_count=int(publisher_count or 0),
                )
                for event, article_count, publisher_count in rows
            ]

    async def search_intelligence(
        self,
        *,
        query: str,
        limit_per_type: int = 12,
        include_claims: bool = False,
    ) -> IntelligenceSearchView:
        # Backwards-compatible entry point retained for integrations written
        # before v1.17. New API paths use the dedicated FTS search service.
        from newsintel.application.search.service import IntelligenceSearchService

        return await IntelligenceSearchService(self._session_factory).search(
            query=query,
            limit=min(100, max(1, limit_per_type * 3)),
            include_claims=include_claims,
            include_entities=include_claims,
        )

    async def get_event(self, event_id: UUID) -> EventDetailView | None:
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            articles = (
                await session.scalars(
                    select(ArticleModel)
                    .where(ArticleModel.event_id == event.id)
                    .order_by(desc(ArticleModel.first_observed_at))
                )
            ).all()
            return EventDetailView(
                id=event.id,
                slug=event.slug,
                title=event.title,
                lifecycle_status=event.lifecycle_status,
                assignment_status=event.assignment_status,
                first_detected_at=event.first_detected_at,
                last_material_change_at=event.last_material_change_at,
                metadata=event.metadata_,
                created_at=event.created_at,
                updated_at=event.updated_at,
                articles=[
                    await self._summary_for_article(session, article)
                    for article in articles
                ],
            )

    async def get_event_dossier(self, event_id: UUID) -> EventDossierView | None:
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            articles = list(
                (
                    await session.scalars(
                        select(ArticleModel)
                        .where(ArticleModel.event_id == event.id)
                        .order_by(desc(ArticleModel.first_observed_at))
                    )
                ).all()
            )
            article_ids = [article.id for article in articles]
            summaries = [await self._summary_for_article(session, article) for article in articles]
            detail = EventDetailView(
                id=event.id,
                slug=event.slug,
                title=event.title,
                lifecycle_status=event.lifecycle_status,
                assignment_status=event.assignment_status,
                first_detected_at=event.first_detected_at,
                last_material_change_at=event.last_material_change_at,
                metadata=event.metadata_,
                created_at=event.created_at,
                updated_at=event.updated_at,
                articles=summaries,
            )
            if not article_ids:
                return EventDossierView(
                    event=detail,
                    latest_claim_count=0,
                    verified_claim_count=0,
                    unresolved_claim_count=0,
                    independent_evidence_link_count=0,
                    independent_lineage_count=0,
                    primary_evidence_link_count=0,
                    contradiction_evidence_link_count=0,
                )

            versions = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.article_id.in_(article_ids))
                        .order_by(ArticleVersionModel.article_id, desc(ArticleVersionModel.version_number))
                    )
                ).all()
            )
            latest_by_article: dict[UUID, ArticleVersionModel] = {}
            for version in versions:
                latest_by_article.setdefault(version.article_id, version)
            latest_version_ids = [version.id for version in latest_by_article.values()]
            claims = list(
                (
                    await session.scalars(
                        select(ArticleClaimModel)
                        .where(ArticleClaimModel.article_version_id.in_(latest_version_ids))
                        .order_by(ArticleClaimModel.created_at, ArticleClaimModel.sentence_index)
                    )
                ).all()
            ) if latest_version_ids else []
            links_by_claim, verification_by_claim = await _evidence_maps(session, claims)
            article_by_id = {article.id: article for article in articles}

            dossier_claims: list[EventDossierClaimView] = []
            verification_counts: dict[str, int] = defaultdict(int)
            independent_total = primary_total = contradiction_total = 0
            ownership_reduced_total = circular_total = near_duplicate_total = 0
            verified_claim_count = 0
            unresolved_claim_count = 0
            decided_labels = {"supported", "contradicted", "disputed", "misleading"}
            unresolved_labels = {"unsupported", "not_checkable", "insufficient_evidence", ""}
            for claim in claims:
                links = links_by_claim.get(claim.id, [])
                independent = [
                    link
                    for link in links
                    if link.independence_score > 0
                    and link.relationship != "origin"
                    and link.source_type != "originating_article"
                ]
                lineage_keys = {_lineage_key_for_link(link) for link in independent}
                primary = [link for link in independent if bool(link.metadata_.get("primary_source"))]
                contradictions = [
                    link for link in independent if link.relationship in {"contradict", "contradicted", "dispute", "disputed"}
                ]
                ownership_reduced = [link for link in independent if _ownership_reduced(link)]
                circular = [link for link in independent if bool(link.metadata_.get("circular_sourcing_detected"))]
                near_duplicates = [link for link in independent if _near_duplicate_evidence(link)]
                independent_total += len(independent)
                primary_total += len(primary)
                contradiction_total += len(contradictions)
                ownership_reduced_total += len(ownership_reduced)
                circular_total += len(circular)
                near_duplicate_total += len(near_duplicates)
                verification = verification_by_claim.get(claim.id)
                label = verification.label if verification else ""
                verification_counts[label or "unverified"] += 1
                if label in decided_labels:
                    verified_claim_count += 1
                if label in unresolved_labels:
                    unresolved_claim_count += 1
                article = article_by_id.get(claim.article_id)
                dossier_claims.append(
                    EventDossierClaimView(
                        id=claim.id,
                        article_id=claim.article_id,
                        article_title=article.title if article else "Linked article",
                        claim_text=claim.claim_text,
                        claim_type=_as_str(claim.extraction_features.get("claim_type")),
                        verification_label=label or None,
                        verification_confidence=(verification.confidence_score if verification else None),
                        evidence_link_count=len(links),
                        independent_evidence_count=len(independent),
                        independent_lineage_count=len(lineage_keys),
                        primary_evidence_count=len(primary),
                        contradiction_evidence_count=len(contradictions),
                        ownership_reduced_evidence_count=len(ownership_reduced),
                        circular_sourcing_count=len(circular),
                        near_duplicate_evidence_count=len(near_duplicates),
                        same_lineage_duplicate_count=max(0, len(independent) - len(lineage_keys)),
                    )
                )

            publisher_counts: dict[UUID, int] = defaultdict(int)
            for article in articles:
                publisher_counts[article.publisher_id] += 1
            publishers = list(
                (
                    await session.scalars(
                        select(PublisherModel).where(PublisherModel.id.in_(list(publisher_counts)))
                    )
                ).all()
            )
            publisher_by_id = {publisher.id: publisher for publisher in publishers}
            publisher_breakdown = [
                EventPublisherBreakdownView(
                    publisher_id=publisher_id,
                    publisher_name=(publisher_by_id[publisher_id].name if publisher_id in publisher_by_id else str(publisher_id)),
                    article_count=count,
                )
                for publisher_id, count in sorted(
                    publisher_counts.items(), key=lambda item: (-item[1], str(item[0]))
                )
            ]
            dossier_claims.sort(
                key=lambda item: (
                    -(item.primary_evidence_count),
                    -(item.independent_evidence_count),
                    item.article_title.lower(),
                    item.claim_text.lower(),
                )
            )
            lineage_breakdown = _summarize_lineages(links_by_claim)
            return EventDossierView(
                event=detail,
                latest_claim_count=len(claims),
                verified_claim_count=verified_claim_count,
                unresolved_claim_count=unresolved_claim_count,
                independent_evidence_link_count=independent_total,
                independent_lineage_count=len(lineage_breakdown),
                primary_evidence_link_count=primary_total,
                contradiction_evidence_link_count=contradiction_total,
                ownership_reduced_evidence_link_count=ownership_reduced_total,
                circular_sourcing_link_count=circular_total,
                near_duplicate_evidence_link_count=near_duplicate_total,
                verification_counts=dict(sorted(verification_counts.items())),
                publisher_breakdown=publisher_breakdown,
                lineage_breakdown=lineage_breakdown,
                claims=dossier_claims,
            )

    async def get_claim_investigation(self, claim_id: UUID) -> ClaimInvestigationView | None:
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            article = await session.get(ArticleModel, claim.article_id)
            if article is None:
                return None
            publisher = await session.get(PublisherModel, article.publisher_id)
            links = list((await session.scalars(
                select(ClaimEvidenceLinkModel)
                .where(ClaimEvidenceLinkModel.claim_id == claim_id)
                .order_by(ClaimEvidenceLinkModel.retrieved_at)
            )).all())
            latest_search = await session.scalar(
                select(EvidenceSearchRunModel)
                .where(EvidenceSearchRunModel.claim_id == claim_id)
                .order_by(desc(EvidenceSearchRunModel.created_at))
                .limit(1)
            )
            latest_conflict = await session.scalar(
                select(ClaimConflictResolutionModel)
                .where(ClaimConflictResolutionModel.claim_id == claim_id)
                .order_by(desc(ClaimConflictResolutionModel.created_at))
                .limit(1)
            )
            review_flags = list((await session.scalars(
                select(ClaimReviewFlagModel)
                .where(ClaimReviewFlagModel.claim_id == claim_id)
                .order_by(desc(ClaimReviewFlagModel.created_at))
            )).all())
            verifications = list((await session.scalars(
                select(ClaimVerificationModel)
                .where(ClaimVerificationModel.claim_id == claim_id)
                .order_by(desc(ClaimVerificationModel.created_at))
                .limit(20)
            )).all())
            return ClaimInvestigationView(
                claim=await self._claim_view(session, claim),
                article_title=article.title,
                event_id=article.event_id,
                publisher_name=publisher.name if publisher else str(article.publisher_id),
                lineages=_summarize_lineages({claim.id: links}),
                latest_search_run=(
                    ClaimEvidenceSearchRunSummaryView(
                        id=latest_search.id,
                        status=latest_search.status,
                        planner_version=latest_search.planner_version,
                        retrieval_complete=latest_search.retrieval_complete,
                        source_count=latest_search.source_count,
                        evidence_count=latest_search.evidence_count,
                        started_at=latest_search.started_at,
                        completed_at=latest_search.completed_at,
                        plan=latest_search.plan,
                        metadata=latest_search.metadata_,
                    ) if latest_search else None
                ),
                latest_conflict=(
                    ClaimConflictSummaryView(
                        id=latest_conflict.id,
                        state=latest_conflict.state,
                        confidence=latest_conflict.confidence,
                        support_weight=latest_conflict.support_weight,
                        contradiction_weight=latest_conflict.contradiction_weight,
                        dispute_weight=latest_conflict.dispute_weight,
                        temporal_update_weight=latest_conflict.temporal_update_weight,
                        independent_lineage_count=latest_conflict.independent_lineage_count,
                        primary_support=latest_conflict.primary_support,
                        primary_contradiction=latest_conflict.primary_contradiction,
                        resolver_version=latest_conflict.resolver_version,
                        metadata=latest_conflict.metadata_,
                        created_at=latest_conflict.created_at,
                    ) if latest_conflict else None
                ),
                review_flags=[
                    ClaimReviewFlagSummaryView(
                        id=item.id,
                        state=item.state,
                        severity=item.severity,
                        actions=list(item.actions),
                        reason=item.reason,
                        resolved_at=item.resolved_at,
                        created_at=item.created_at,
                    )
                    for item in review_flags
                ],
                verification_history=[
                    ClaimVerificationView(
                        id=item.id,
                        label=item.label,
                        confidence_score=item.confidence_score,
                        methodology_version=item.methodology_version,
                        confidence_factors=item.confidence_factors,
                        reasoning_trace=item.reasoning_trace,
                        created_at=item.created_at,
                    )
                    for item in verifications
                ],
            )

    async def get_article_claims(self, article_id: UUID) -> list[ArticleClaimView] | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            claims = (
                await session.scalars(
                    select(ArticleClaimModel)
                    .where(ArticleClaimModel.article_id == article_id)
                    .order_by(
                        ArticleClaimModel.created_at,
                        ArticleClaimModel.sentence_index,
                    )
                )
            ).all()
            return [await self._claim_view(session, claim) for claim in claims]

    async def get_article_quality(
        self,
        article_id: UUID,
    ) -> ArticleQualityProfileView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            versions = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.article_id == article_id)
                        .order_by(ArticleVersionModel.version_number)
                    )
                ).all()
            )
            latest = versions[-1] if versions else None
            publisher_reliability = await session.scalar(
                select(PublisherReliabilitySnapshotModel)
                .where(
                    PublisherReliabilitySnapshotModel.publisher_id == article.publisher_id,
                    PublisherReliabilitySnapshotModel.topic_key == "all",
                )
                .order_by(PublisherReliabilitySnapshotModel.created_at.desc())
                .limit(1)
            )
            claims: list[ArticleClaimModel] = []
            if latest is not None:
                claims = list(
                    (
                        await session.scalars(
                            select(ArticleClaimModel)
                            .where(ArticleClaimModel.article_version_id == latest.id)
                            .order_by(ArticleClaimModel.sentence_index)
                        )
                    ).all()
                )
            links_by_claim, verifications_by_claim = await _evidence_maps(session, claims)
            completed_search_claim_ids: set[UUID] = set()
            claim_ids = [claim.id for claim in claims]
            if claim_ids:
                completed_search_claim_ids = set(
                    (
                        await session.scalars(
                            select(EvidenceSearchRunModel.claim_id).where(
                                EvidenceSearchRunModel.claim_id.in_(claim_ids),
                                EvidenceSearchRunModel.retrieval_complete.is_(True),
                            )
                        )
                    ).all()
                )
            latest_conflicts: dict[UUID, ClaimConflictResolutionModel] = {}
            if claim_ids:
                conflict_rows = list(
                    (
                        await session.scalars(
                            select(ClaimConflictResolutionModel)
                            .where(ClaimConflictResolutionModel.claim_id.in_(claim_ids))
                            .order_by(ClaimConflictResolutionModel.created_at)
                        )
                    ).all()
                )
                for conflict in conflict_rows:
                    latest_conflicts[conflict.claim_id] = conflict
            conflict_state_counts: dict[str, int] = defaultdict(int)
            for conflict in latest_conflicts.values():
                conflict_state_counts[conflict.state] += 1

            review_required_claim_ids: set[UUID] = set()
            critical_review_claim_ids: set[UUID] = set()
            if claim_ids:
                review_flags = list(
                    (
                        await session.scalars(
                            select(ClaimReviewFlagModel).where(
                                ClaimReviewFlagModel.claim_id.in_(claim_ids),
                                ClaimReviewFlagModel.state == "review_required",
                            )
                        )
                    ).all()
                )
                review_required_claim_ids = {item.claim_id for item in review_flags}
                critical_review_claim_ids = {
                    item.claim_id for item in review_flags if item.severity == "critical"
                }

            claim_signals: list[ClaimQualitySignal] = []
            for claim in claims:
                links = links_by_claim.get(claim.id, [])
                independent = [
                    link
                    for link in links
                    if link.independence_score > 0
                    and link.relationship != "origin"
                    and link.source_type != "originating_article"
                ]
                domains = tuple(
                    sorted(
                        {
                            domain
                            for link in independent
                            if (domain := evidence_domain(link.source_url))
                        }
                    )
                )
                verification = verifications_by_claim.get(claim.id)
                checkability = claim.extraction_features.get("checkability_score")
                claim_signals.append(
                    ClaimQualitySignal(
                        checkability_score=(
                            float(checkability)
                            if isinstance(checkability, int | float)
                            else None
                        ),
                        claim_type=_as_str(claim.extraction_features.get("claim_type")),
                        verification_label=verification.label if verification else None,
                        verification_confidence=(
                            verification.confidence_score if verification else None
                        ),
                        independent_evidence_count=len(independent),
                        independent_evidence_weight=sum(
                            max(0.0, min(1.0, float(link.independence_score)))
                            for link in independent
                        ),
                        evidence_domains=domains,
                        primary_evidence_count=sum(
                            bool(link.metadata_.get("primary_source")) for link in independent
                        ),
                        temporally_resolved_evidence_count=sum(
                            link.metadata_.get("temporal_relation")
                            not in {None, "", "unknown"}
                            for link in independent
                        ),
                        evidence_search_complete=claim.id in completed_search_claim_ids,
                    )
                )
            assessment = assess_article_quality(
                ArticleQualitySignals(
                    extraction_quality_score=_extraction_quality_score(latest),
                    extraction_warnings=(
                        tuple(latest.extraction_warnings) if latest is not None else ()
                    ),
                    claims=tuple(claim_signals),
                    version_count=len(versions),
                    latest_text=latest.text_content if latest is not None else "",
                    publisher_reliability_score=(
                        publisher_reliability.posterior_mean
                        if publisher_reliability is not None
                        else None
                    ),
                    publisher_reliability_sample_size=(
                        int(round(publisher_reliability.effective_sample_size))
                        if publisher_reliability is not None
                        else None
                    ),
                )
            )
            return ArticleQualityProfileView(
                article_id=article_id,
                version_id=latest.id if latest else None,
                methodology_version=assessment.methodology_version,
                assessment_scope=assessment.assessment_scope,
                overall_evidence_readiness=assessment.overall_evidence_readiness,
                dimensions=[
                    QualityDimensionView(
                        name=item.name,
                        score=item.score,
                        status=item.status.value,
                        explanation=item.explanation,
                        sample_size=item.sample_size,
                    )
                    for item in assessment.dimensions
                ],
                claim_count=assessment.claim_count,
                checkable_claim_count=assessment.checkable_claim_count,
                verified_claim_count=assessment.verified_claim_count,
                independent_evidence_links=assessment.independent_evidence_links,
                evidence_domain_count=assessment.evidence_domain_count,
                unresolved_conflict_claim_count=conflict_state_counts.get("unresolved_conflict", 0),
                temporal_evolution_claim_count=conflict_state_counts.get("temporal_evolution", 0),
                resolved_conflict_claim_count=(
                    conflict_state_counts.get("resolved_support", 0)
                    + conflict_state_counts.get("resolved_contradiction", 0)
                ),
                latest_conflict_states=dict(sorted(conflict_state_counts.items())),
                review_required_claim_count=len(review_required_claim_ids),
                critical_review_claim_count=len(critical_review_claim_ids),
                generated_at=datetime.now(UTC),
            )

    async def get_article_version_history(
        self,
        article_id: UUID,
    ) -> ArticleVersionHistoryView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            versions = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.article_id == article_id)
                        .order_by(ArticleVersionModel.version_number)
                    )
                ).all()
            )
            entries: list[ArticleVersionHistoryEntryView] = []
            previous: ArticleVersionModel | None = None
            for version in versions:
                diff = (
                    diff_article_versions(
                        old_title=previous.title,
                        old_text=previous.text_content,
                        new_title=version.title,
                        new_text=version.text_content,
                    )
                    if previous is not None
                    else None
                )
                entries.append(
                    ArticleVersionHistoryEntryView(
                        version_id=version.id,
                        version_number=version.version_number,
                        title=version.title,
                        source_url=version.source_url,
                        final_url=version.final_url,
                        published_at=version.published_at,
                        retrieved_at=version.retrieved_at,
                        content_sha256=version.content_sha256,
                        extraction_method=version.extraction_method,
                        extraction_warnings=list(version.extraction_warnings),
                        diff_from_previous=_diff_view(diff) if diff else None,
                    )
                )
                previous = version
            return ArticleVersionHistoryView(
                article_id=article_id,
                canonical_url=article.canonical_url,
                version_count=len(versions),
                entries=entries,
            )

    async def get_article_claim_history(
        self,
        article_id: UUID,
    ) -> ArticleClaimHistoryView | None:
        async with self._session_factory() as session:
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            versions = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.article_id == article_id)
                        .order_by(ArticleVersionModel.version_number)
                    )
                ).all()
            )
            version_by_id = {version.id: version for version in versions}
            latest_number = versions[-1].version_number if versions else None
            claims = list(
                (
                    await session.scalars(
                        select(ArticleClaimModel)
                        .where(ArticleClaimModel.article_id == article_id)
                        .order_by(ArticleClaimModel.created_at, ArticleClaimModel.sentence_index)
                    )
                ).all()
            )
            _, verifications = await _evidence_maps(session, claims)
            verification_histories = await _verification_history_map(session, claims)
            grouped: dict[str, list[ArticleClaimModel]] = defaultdict(list)
            for claim in claims:
                family_key = _claim_family_key(claim)
                grouped[family_key].append(claim)

            families: list[ClaimHistoryFamilyView] = []
            for family_key, members in grouped.items():
                revisions: list[ClaimHistoryRevisionView] = []
                version_numbers: list[int] = []
                texts: set[str] = set()
                canonical_keys: set[str] = set()
                family_text: str | None = None
                for claim in members:
                    version = version_by_id.get(claim.article_version_id)
                    if version is None:
                        continue
                    version_numbers.append(version.version_number)
                    texts.add(claim.claim_text)
                    canonical_key = claim.extraction_features.get("canonical_key")
                    if isinstance(canonical_key, str):
                        canonical_keys.add(canonical_key)
                    raw_family_text = claim.extraction_features.get("claim_family_text")
                    if family_text is None and isinstance(raw_family_text, str):
                        family_text = raw_family_text
                    verification = verifications.get(claim.id)
                    revisions.append(
                        ClaimHistoryRevisionView(
                            claim_id=claim.id,
                            article_version_id=claim.article_version_id,
                            version_number=version.version_number,
                            retrieved_at=version.retrieved_at,
                            claim_text=claim.claim_text,
                            claim_type=_as_str(claim.extraction_features.get("claim_type")),
                            quantities=_dict_list(claim.extraction_features.get("quantities")),
                            temporal_references=_dict_list(
                                claim.extraction_features.get("temporal_references")
                            ),
                            verification_label=verification.label if verification else None,
                            verification_confidence=(
                                verification.confidence_score if verification else None
                            ),
                            verification_history=[
                                ClaimVerificationSnapshotView(
                                    label=item.label,
                                    confidence_score=item.confidence_score,
                                    methodology_version=item.methodology_version,
                                    created_at=item.created_at,
                                )
                                for item in verification_histories.get(claim.id, [])
                            ],
                        )
                    )
                if not revisions:
                    continue
                revisions.sort(key=lambda item: (item.version_number, item.retrieved_at))
                families.append(
                    ClaimHistoryFamilyView(
                        family_key=family_key,
                        family_text=family_text,
                        first_version_number=min(version_numbers),
                        last_version_number=max(version_numbers),
                        active_in_latest_version=(
                            latest_number is not None and latest_number in version_numbers
                        ),
                        changed_across_versions=(
                            len(texts) > 1 or len(canonical_keys) > 1
                        ),
                        revisions=revisions,
                    )
                )
            families.sort(
                key=lambda item: (
                    item.first_version_number,
                    item.last_version_number,
                    item.family_key,
                )
            )
            return ArticleClaimHistoryView(
                article_id=article_id,
                latest_version_number=latest_number,
                families=families,
            )

    async def get_event_timeline(self, event_id: UUID) -> EventTimelineView | None:
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            articles = list(
                (
                    await session.scalars(
                        select(ArticleModel)
                        .where(ArticleModel.event_id == event_id)
                        .order_by(ArticleModel.first_observed_at)
                    )
                ).all()
            )
            article_ids = [article.id for article in articles]
            versions: list[ArticleVersionModel] = []
            claims: list[ArticleClaimModel] = []
            if article_ids:
                versions = list(
                    (
                        await session.scalars(
                            select(ArticleVersionModel)
                            .where(ArticleVersionModel.article_id.in_(article_ids))
                            .order_by(
                                ArticleVersionModel.article_id,
                                ArticleVersionModel.version_number,
                            )
                        )
                    ).all()
                )
                claims = list(
                    (
                        await session.scalars(
                            select(ArticleClaimModel).where(
                                ArticleClaimModel.article_id.in_(article_ids)
                            )
                        )
                    ).all()
                )
            claim_counts: dict[UUID, int] = defaultdict(int)
            for claim in claims:
                claim_counts[claim.article_version_id] += 1
            article_by_id = {article.id: article for article in articles}
            versions_by_article: dict[UUID, list[ArticleVersionModel]] = defaultdict(list)
            for version in versions:
                versions_by_article[version.article_id].append(version)

            points: list[EventTimelinePointView] = [
                EventTimelinePointView(
                    occurred_at=event.first_detected_at,
                    point_type="event_detected",
                    title=event.title,
                    metadata={
                        "assignment_status": event.assignment_status,
                        "lifecycle_status": event.lifecycle_status,
                    },
                )
            ]
            for article_id, article_versions in versions_by_article.items():
                article = article_by_id[article_id]
                previous: ArticleVersionModel | None = None
                for version in article_versions:
                    diff = (
                        diff_article_versions(
                            old_title=previous.title,
                            old_text=previous.text_content,
                            new_title=version.title,
                            new_text=version.text_content,
                        )
                        if previous is not None
                        else None
                    )
                    points.append(
                        EventTimelinePointView(
                            occurred_at=version.retrieved_at,
                            point_type=(
                                "article_observed" if previous is None else "article_revision"
                            ),
                            article_id=article.id,
                            article_version_id=version.id,
                            version_number=version.version_number,
                            publisher_id=article.publisher_id,
                            title=version.title,
                            source_url=version.final_url,
                            published_at=version.published_at,
                            claim_count=claim_counts.get(version.id, 0),
                            material_change_count=(
                                diff.material_change_count if diff else 0
                            ),
                            numeric_change_count=(diff.numeric_change_count if diff else 0),
                            temporal_change_count=(
                                diff.temporal_change_count if diff else 0
                            ),
                            metadata={
                                "content_sha256": version.content_sha256,
                                "extraction_method": version.extraction_method,
                                "extraction_warnings": list(version.extraction_warnings),
                            },
                        )
                    )
                    previous = version
            points.sort(key=lambda item: (item.occurred_at, item.point_type))
            return EventTimelineView(
                event_id=event.id,
                timeline_basis="system_observation_time_with_publication_context",
                time_semantics_note=(
                    "timeline_points.occurred_at is when the platform observed a stored "
                    "version; published_at is retained separately and neither is assumed "
                    "to equal the real-world event time."
                ),
                title=event.title,
                first_detected_at=event.first_detected_at,
                last_material_change_at=event.last_material_change_at,
                article_count=len(articles),
                publisher_count=len({article.publisher_id for article in articles}),
                timeline_points=points,
            )

    async def _summary_for_article(
        self,
        session: AsyncSession,
        article: ArticleModel,
    ) -> ArticleSummaryView:
        latest = await self._latest_version(session, article.id)
        context = (
            await self._historical_context_for_version(session, latest.id)
            if latest is not None
            else None
        )
        job = (
            await self._historical_job_for_version(session, latest.id)
            if latest is not None and context is None
            else None
        )
        return _summary_from_models(article, latest, context, job)

    async def _historical_context_for_version(
        self,
        session: AsyncSession,
        version_id: UUID,
    ) -> ArticleHistoricalContextModel | None:
        return await session.scalar(
            select(ArticleHistoricalContextModel)
            .where(ArticleHistoricalContextModel.article_version_id == version_id)
            .order_by(ArticleHistoricalContextModel.generated_at.desc())
            .limit(1)
        )

    async def _historical_job_for_version(
        self,
        session: AsyncSession,
        version_id: UUID,
    ) -> ArticleHistoricalEnrichmentJobModel | None:
        return await session.scalar(
            select(ArticleHistoricalEnrichmentJobModel)
            .where(ArticleHistoricalEnrichmentJobModel.article_version_id == version_id)
            .limit(1)
        )

    async def _latest_version(
        self,
        session: AsyncSession,
        article_id: UUID,
    ) -> ArticleVersionModel | None:
        return cast(
            ArticleVersionModel | None,
            await session.scalar(
                select(ArticleVersionModel)
                .where(ArticleVersionModel.article_id == article_id)
                .order_by(desc(ArticleVersionModel.version_number))
                .limit(1)
            ),
        )

    async def _claim_view(
        self,
        session: AsyncSession,
        claim: ArticleClaimModel,
    ) -> ArticleClaimView:
        evidence_links = (
            await session.scalars(
                select(ClaimEvidenceLinkModel)
                .where(ClaimEvidenceLinkModel.claim_id == claim.id)
                .order_by(ClaimEvidenceLinkModel.retrieved_at)
            )
        ).all()
        verification = await session.scalar(
            select(ClaimVerificationModel)
            .where(ClaimVerificationModel.claim_id == claim.id)
            .order_by(desc(ClaimVerificationModel.created_at))
            .limit(1)
        )
        return ArticleClaimView(
            id=claim.id,
            article_id=claim.article_id,
            article_version_id=claim.article_version_id,
            claim_text=claim.claim_text,
            claim_sha256=claim.claim_sha256,
            sentence_index=claim.sentence_index,
            extractor_version=claim.extractor_version,
            extraction_features=claim.extraction_features,
            created_at=claim.created_at,
            evidence_links=[
                ClaimEvidenceLinkView(
                    id=link.id,
                    source_url=link.source_url,
                    source_type=link.source_type,
                    relationship=link.relationship,
                    retrieved_at=link.retrieved_at,
                    similarity_score=link.similarity_score,
                    independence_score=link.independence_score,
                    metadata=link.metadata_,
                )
                for link in evidence_links
            ],
            latest_verification=(
                ClaimVerificationView(
                    id=verification.id,
                    label=verification.label,
                    confidence_score=verification.confidence_score,
                    methodology_version=verification.methodology_version,
                    confidence_factors=verification.confidence_factors,
                    reasoning_trace=verification.reasoning_trace,
                    created_at=verification.created_at,
                )
                if verification
                else None
            ),
        )


async def _evidence_maps(
    session: AsyncSession,
    claims: list[ArticleClaimModel],
) -> tuple[
    dict[UUID, list[ClaimEvidenceLinkModel]],
    dict[UUID, ClaimVerificationModel],
]:
    claim_ids = [claim.id for claim in claims]
    if not claim_ids:
        return {}, {}
    links = list(
        (
            await session.scalars(
                select(ClaimEvidenceLinkModel)
                .where(ClaimEvidenceLinkModel.claim_id.in_(claim_ids))
                .order_by(ClaimEvidenceLinkModel.retrieved_at)
            )
        ).all()
    )
    verifications = list(
        (
            await session.scalars(
                select(ClaimVerificationModel)
                .where(ClaimVerificationModel.claim_id.in_(claim_ids))
                .order_by(desc(ClaimVerificationModel.created_at))
            )
        ).all()
    )
    links_by_claim: dict[UUID, list[ClaimEvidenceLinkModel]] = defaultdict(list)
    for link in links:
        links_by_claim[link.claim_id].append(link)
    latest_verification: dict[UUID, ClaimVerificationModel] = {}
    for verification in verifications:
        latest_verification.setdefault(verification.claim_id, verification)
    return dict(links_by_claim), latest_verification


async def _verification_history_map(
    session: AsyncSession,
    claims: list[ArticleClaimModel],
) -> dict[UUID, list[ClaimVerificationModel]]:
    claim_ids = [claim.id for claim in claims]
    if not claim_ids:
        return {}
    rows = list(
        (
            await session.scalars(
                select(ClaimVerificationModel)
                .where(ClaimVerificationModel.claim_id.in_(claim_ids))
                .order_by(ClaimVerificationModel.created_at)
            )
        ).all()
    )
    grouped: dict[UUID, list[ClaimVerificationModel]] = defaultdict(list)
    for row in rows:
        grouped[row.claim_id].append(row)
    return dict(grouped)


def _literal_like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _search_snippet(text: str, needle: str, *, radius: int = 105) -> str:
    normalized_text = " ".join((text or "").split())
    if not normalized_text:
        return ""
    lower = normalized_text.casefold()
    target = needle.casefold()
    index = lower.find(target)
    if index < 0:
        return normalized_text[: radius * 2] + ("…" if len(normalized_text) > radius * 2 else "")
    start = max(0, index - radius)
    end = min(len(normalized_text), index + len(needle) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(normalized_text) else ""
    return prefix + normalized_text[start:end] + suffix


def _diff_view(diff: VersionDiff) -> ArticleVersionDiffView:
    return ArticleVersionDiffView(
        methodology_version=diff.methodology_version,
        added_count=diff.added_count,
        removed_count=diff.removed_count,
        replaced_count=diff.replaced_count,
        numeric_change_count=diff.numeric_change_count,
        temporal_change_count=diff.temporal_change_count,
        material_change_count=diff.material_change_count,
        changes=[
            ArticleVersionChangeView(
                kind=change.kind.value,
                significance=change.significance.value,
                old_text=change.old_text,
                new_text=change.new_text,
                old_sentence_index=change.old_sentence_index,
                new_sentence_index=change.new_sentence_index,
                similarity=change.similarity,
                metadata=change.metadata or {},
            )
            for change in diff.changes
        ],
    )


def _lineage_key_for_link(link: ClaimEvidenceLinkModel) -> str:
    value = link.metadata_.get("lineage_key")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if link.evidence_article_id is not None:
        return f"article:{link.evidence_article_id}"
    return f"url:{link.source_url}"


def _ownership_reduced(link: ClaimEvidenceLinkModel) -> bool:
    if bool(link.metadata_.get("shared_ownership_group")):
        return True
    cap = link.metadata_.get("ownership_independence_cap")
    return isinstance(cap, int | float) and float(cap) < 1.0


def _near_duplicate_evidence(link: ClaimEvidenceLinkModel) -> bool:
    similarity = link.metadata_.get("max_prior_lineage_similarity")
    return isinstance(similarity, int | float) and float(similarity) >= 0.70


def _summarize_lineages(
    links_by_claim: dict[UUID, list[ClaimEvidenceLinkModel]],
) -> list[EvidenceLineageSummaryView]:
    grouped: dict[str, dict[str, object]] = {}
    for claim_id, links in links_by_claim.items():
        for link in links:
            if link.relationship == "origin" or link.source_type == "originating_article":
                continue
            key = _lineage_key_for_link(link)
            bucket = grouped.setdefault(key, {
                "claim_ids": set(),
                "urls": set(),
                "relationships": set(),
                "link_count": 0,
                "max_independence": 0.0,
                "primary": False,
                "ownership": False,
                "circular": False,
            })
            bucket["claim_ids"].add(claim_id)
            bucket["urls"].add(link.source_url)
            bucket["relationships"].add(link.relationship)
            bucket["link_count"] = int(bucket["link_count"]) + 1
            bucket["max_independence"] = max(float(bucket["max_independence"]), float(link.independence_score))
            bucket["primary"] = bool(bucket["primary"]) or bool(link.metadata_.get("primary_source"))
            bucket["ownership"] = bool(bucket["ownership"]) or _ownership_reduced(link)
            bucket["circular"] = bool(bucket["circular"]) or bool(link.metadata_.get("circular_sourcing_detected"))
    rows = [
        EvidenceLineageSummaryView(
            lineage_key=key,
            link_count=int(value["link_count"]),
            claim_count=len(value["claim_ids"]),
            source_count=len(value["urls"]),
            source_urls=sorted(str(item) for item in value["urls"])[:8],
            max_independence_score=round(float(value["max_independence"]), 4),
            primary_source_present=bool(value["primary"]),
            shared_ownership_present=bool(value["ownership"]),
            circular_sourcing_present=bool(value["circular"]),
            relationships=sorted(str(item) for item in value["relationships"]),
        )
        for key, value in grouped.items()
    ]
    rows.sort(key=lambda item: (-item.max_independence_score, -item.claim_count, item.lineage_key))
    return rows


def _claim_family_key(claim: ArticleClaimModel) -> str:
    for key in ("claim_family_key", "canonical_key"):
        value = claim.extraction_features.get(key)
        if isinstance(value, str) and value:
            return value
    return claim.claim_sha256


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None



def _summary_from_models(
    article: ArticleModel,
    latest: ArticleVersionModel | None,
    context: ArticleHistoricalContextModel | None,
    job: ArticleHistoricalEnrichmentJobModel | None,
) -> ArticleSummaryView:
    summary = dict(context.context_summary) if context is not None else {}
    confidence = summary.get("historical_context_confidence")
    confidence_score = (
        float(confidence.get("score"))
        if isinstance(confidence, dict) and isinstance(confidence.get("score"), int | float)
        else None
    )
    depth = summary.get("historical_depth")
    change_pattern = summary.get("change_pattern")
    history_status = context.status if context is not None else (job.state if job is not None else None)
    return ArticleSummaryView(
        id=article.id,
        event_id=article.event_id,
        publisher_id=article.publisher_id,
        canonical_url=article.canonical_url,
        title=article.title,
        language=article.language,
        published_at=article.published_at,
        first_observed_at=article.first_observed_at,
        latest_version_id=latest.id if latest is not None else None,
        latest_version_number=latest.version_number if latest is not None else None,
        latest_extraction_method=latest.extraction_method if latest is not None else None,
        latest_extraction_warnings=list(latest.extraction_warnings) if latest is not None else [],
        latest_extraction_quality_score=_extraction_quality_score(latest),
        latest_extraction_fidelity_score=_extraction_fidelity_score(latest),
        latest_extraction_fidelity_label=_extraction_fidelity_label(latest),
        word_count=_word_count(latest) if latest is not None else None,
        historical_context_status=history_status,
        historical_depth=depth if isinstance(depth, str) else None,
        historical_confidence_score=confidence_score,
        historical_change_pattern=change_pattern if isinstance(change_pattern, str) else None,
    )

def _historical_context_view(row: ArticleHistoricalContextModel) -> ArticleHistoricalContextView:
    return ArticleHistoricalContextView(
        article_id=row.article_id,
        article_version_id=row.article_version_id,
        event_id=row.event_id,
        methodology_version=row.methodology_version,
        status=row.status,
        cutoff_at=row.cutoff_at,
        queries=list(row.queries),
        same_event_history=list(row.same_event_history),
        prior_claim_history=list(row.prior_claim_history),
        internal_matches=list(row.internal_matches),
        external_matches=list(row.external_matches),
        provider_statuses=list(row.provider_statuses),
        timeline_summary=dict(row.timeline_summary),
        context_summary=dict(row.context_summary),
        generated_at=row.generated_at,
    )


def _historical_job_view(row: ArticleHistoricalEnrichmentJobModel) -> HistoricalEnrichmentStateView:
    return HistoricalEnrichmentStateView(
        state=row.state,
        attempt_count=row.attempt_count,
        refresh_count=row.refresh_count,
        last_refresh_reason=row.last_refresh_reason,
        last_reconciled_at=row.last_reconciled_at,
        last_error=row.last_error,
        next_attempt_at=row.next_attempt_at,
        updated_at=row.updated_at,
    )


def _version_view(version: ArticleVersionModel) -> ArticleVersionView:
    return ArticleVersionView(
        id=version.id,
        version_number=version.version_number,
        source_url=version.source_url,
        final_url=version.final_url,
        title=version.title,
        byline=version.byline,
        language=version.language,
        published_at=version.published_at,
        retrieved_at=version.retrieved_at,
        content_sha256=version.content_sha256,
        extraction_method=version.extraction_method,
        extraction_warnings=version.extraction_warnings,
        extraction_quality_score=_extraction_quality_score(version),
        extraction_fidelity_score=_extraction_fidelity_score(version),
        extraction_fidelity_label=_extraction_fidelity_label(version),
        extraction_fidelity_discrepancies=_extraction_fidelity_discrepancies(version),
        browser_rendered=bool(version.metadata_.get("browser_rendered")),
        raw_artifact_uri=_raw_artifact_uri(version),
        word_count=_word_count(version),
        text_content=version.text_content,
        created_at=version.created_at,
    )


def _word_count(version: ArticleVersionModel | None) -> int:
    if version is None:
        return 0
    metadata_word_count = version.metadata_.get("word_count")
    if isinstance(metadata_word_count, int):
        return metadata_word_count
    return len(version.text_content.split())


def _extraction_quality_score(version: ArticleVersionModel | None) -> float | None:
    if version is None:
        return None
    value = version.metadata_.get("extraction_quality_score")
    if isinstance(value, int | float):
        return float(value)
    return None



def _extraction_fidelity(version: ArticleVersionModel | None) -> dict[str, object] | None:
    if version is None:
        return None
    value = version.metadata_.get("extraction_fidelity")
    return value if isinstance(value, dict) else None


def _extraction_fidelity_score(version: ArticleVersionModel | None) -> float | None:
    fidelity = _extraction_fidelity(version)
    if fidelity is None:
        return None
    value = fidelity.get("score")
    return float(value) if isinstance(value, int | float) else None


def _extraction_fidelity_label(version: ArticleVersionModel | None) -> str | None:
    fidelity = _extraction_fidelity(version)
    if fidelity is None:
        return None
    value = fidelity.get("label")
    return value if isinstance(value, str) else None


def _extraction_fidelity_discrepancies(version: ArticleVersionModel | None) -> list[str]:
    fidelity = _extraction_fidelity(version)
    if fidelity is None:
        return []
    values = fidelity.get("discrepancies")
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]

def _raw_artifact_uri(version: ArticleVersionModel) -> str | None:
    artifact = version.metadata_.get("raw_fetch_artifact")
    if not isinstance(artifact, dict):
        return None
    uri = artifact.get("artifact_uri")
    return uri if isinstance(uri, str) else None
