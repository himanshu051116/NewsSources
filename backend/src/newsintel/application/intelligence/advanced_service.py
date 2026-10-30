from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.evidence.authority_search import (
    AuthorityAdapterType,
    AuthoritySearchExecutor,
    AuthoritySearchSpec,
)
from newsintel.application.intelligence.dto import (
    EvidenceAuthorityExecutionView,
    EvidenceEvaluationCommand,
    EvidenceRetrievalAttemptView,
    EvidenceSearchExecuteCommand,
    EvidenceSearchExecutionView,
    PublisherReliabilityRecomputeCommand,
    PublisherReliabilitySnapshotView,
    TemporalKnowledgeEdgeView,
    TemporalKnowledgeGraphDiffView,
    TemporalKnowledgeGraphView,
    TemporalKnowledgeNodeView,
)
from newsintel.application.intelligence.service import EvidenceIntelligenceService
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.entities import normalize_entity_name
from newsintel.domain.intelligence.knowledge_graph import (
    KnowledgeClaimInput,
    KnowledgeCommitmentInput,
    KnowledgeEvidenceInput,
    KnowledgeVerificationInput,
    build_event_knowledge_graph,
)
from newsintel.domain.intelligence.primary_evidence import EvidenceAuthorityClass
from newsintel.domain.intelligence.reliability import (
    ReliabilityObservation,
    assess_publisher_reliability,
)
from newsintel.domain.intelligence.temporal import derive_temporal_context
from newsintel.domain.intelligence.topics import classify_news_topic
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimVerificationModel,
    CanonicalEntityModel,
    EntityAliasModel,
    EventCommitmentModel,
    EventModel,
    EvidenceAuthorityProfileModel,
    EvidencePassageEvaluationModel,
    EvidenceRetrievalAttemptModel,
    EvidenceSearchRunModel,
    PublisherModel,
    PublisherReliabilitySnapshotModel,
    TemporalKnowledgeEdgeModel,
    TemporalKnowledgeNodeModel,
)


class EvidenceRetrievalService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        fetcher,
    ) -> None:
        self._session_factory = session_factory
        self._executor = AuthoritySearchExecutor(fetcher)
        self._evidence_service = EvidenceIntelligenceService(session_factory)

    async def execute(
        self,
        claim_id: UUID,
        run_id: UUID,
        command: EvidenceSearchExecuteCommand,
    ) -> EvidenceSearchExecutionView | None:
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            run = await session.get(EvidenceSearchRunModel, run_id)
            if claim is None or run is None or run.claim_id != claim_id:
                return None
            authorities = await self._authorities_for_run(session, run, command)
            search_terms = run.plan.get("search_terms") if isinstance(run.plan, dict) else None
            default_query = " ".join(str(item) for item in (search_terms or [])[:4]).strip()
            query = command.query_override or default_query or claim.claim_text

        authority_results: list[EvidenceAuthorityExecutionView] = []
        total_documents = 0
        total_evaluations = 0
        for authority in authorities:
            try:
                adapter_type = AuthorityAdapterType(authority.adapter_type)
            except ValueError:
                adapter_type = AuthorityAdapterType.GENERIC_HTML_SEARCH
            spec = AuthoritySearchSpec(
                authority_id=str(authority.id),
                name=authority.name,
                evidence_class=authority.evidence_class,
                base_url=authority.base_url,
                allowed_domains=tuple(authority.allowed_domains),
                search_url_template=authority.search_url_template,
                adapter_type=adapter_type,
                adapter_config=authority.adapter_config,
            )
            documents, attempts = await self._executor.retrieve(
                spec,
                query=query,
                max_candidates=command.max_candidates_per_authority,
            )
            attempt_views = await self._persist_attempts(
                run_id=run_id,
                authority_id=authority.id,
                attempts=attempts,
            )
            evaluations = 0
            for document in documents:
                try:
                    evidence_class = EvidenceAuthorityClass(authority.evidence_class)
                except ValueError:
                    continue
                result = await self._evidence_service.evaluate_evidence(
                    claim_id,
                    EvidenceEvaluationCommand(
                        source_url=document.final_url,
                        source_type="authority_adapter",
                        evidence_text=document.text,
                        evidence_class=evidence_class,
                        search_run_id=run_id,
                        retrieved_at=datetime.fromisoformat(document.retrieved_at_iso),
                        independence_score=1.0,
                        primary_source=True,
                    ),
                )
                if result is not None:
                    evaluations += 1
            total_documents += len(documents)
            total_evaluations += evaluations
            authority_results.append(
                EvidenceAuthorityExecutionView(
                    authority_id=authority.id,
                    authority_name=authority.name,
                    evidence_class=authority.evidence_class,
                    documents_retrieved=len(documents),
                    evaluations_created=evaluations,
                    attempts=attempt_views,
                )
            )
        await self._mark_run_execution(
            run_id=run_id,
            authority_count=len(authorities),
            document_count=total_documents,
            evaluation_count=total_evaluations,
        )
        return EvidenceSearchExecutionView(
            claim_id=claim_id,
            run_id=run_id,
            authorities_attempted=len(authorities),
            documents_retrieved=total_documents,
            evaluations_created=total_evaluations,
            authority_results=authority_results,
            guardrail=(
                "Only administrator-configured authority domains are searched/fetched. "
                "Automated retrieval does not itself complete the evidence search or convert "
                "retrieved text into factual truth."
            ),
        )

    async def _authorities_for_run(
        self,
        session: AsyncSession,
        run: EvidenceSearchRunModel,
        command: EvidenceSearchExecuteCommand,
    ) -> list[EvidenceAuthorityProfileModel]:
        requirements = run.plan.get("requirements") if isinstance(run.plan, dict) else None
        classes: list[str] = []
        if isinstance(requirements, list):
            for item in requirements:
                if isinstance(item, dict):
                    value = item.get("evidence_class")
                    if isinstance(value, str):
                        classes.append(value)
        statement = select(EvidenceAuthorityProfileModel).where(
            EvidenceAuthorityProfileModel.active.is_(True)
        )
        if command.authority_ids:
            statement = statement.where(EvidenceAuthorityProfileModel.id.in_(command.authority_ids))
        elif classes:
            statement = statement.where(EvidenceAuthorityProfileModel.evidence_class.in_(classes))
        rows = list((await session.scalars(statement.order_by(EvidenceAuthorityProfileModel.name))).all())
        return rows[: command.max_authorities]

    async def _persist_attempts(
        self,
        *,
        run_id: UUID,
        authority_id: UUID,
        attempts,
    ) -> list[EvidenceRetrievalAttemptView]:
        now = datetime.now(UTC)
        views: list[EvidenceRetrievalAttemptView] = []
        async with self._session_factory() as session, session.begin():
            for attempt in attempts:
                model = EvidenceRetrievalAttemptModel(
                    id=uuid7(),
                    search_run_id=run_id,
                    authority_profile_id=authority_id,
                    search_url=attempt.search_url,
                    candidate_url=attempt.candidate_url,
                    status=attempt.status,
                    http_status=attempt.http_status,
                    body_sha256=attempt.body_sha256,
                    error_type=attempt.error_type,
                    error_message=attempt.error_message,
                    metadata_=attempt.metadata,
                    created_at=now,
                )
                session.add(model)
                views.append(_attempt_view(model))
            await session.flush()
        return views

    async def _mark_run_execution(
        self,
        *,
        run_id: UUID,
        authority_count: int,
        document_count: int,
        evaluation_count: int,
    ) -> None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            run = await session.get(EvidenceSearchRunModel, run_id)
            if run is None:
                return
            metadata = dict(run.metadata_)
            executions = list(metadata.get("adapter_executions") or [])
            executions.append(
                {
                    "executed_at": now.isoformat(),
                    "authority_count": authority_count,
                    "document_count": document_count,
                    "evaluation_count": evaluation_count,
                }
            )
            metadata["adapter_executions"] = executions[-20:]
            metadata["automated_authority_retrieval_used"] = True
            run.metadata_ = metadata
            if run.status == "planned":
                run.status = "in_progress"
            run.updated_at = now


class PublisherReliabilityService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def recompute(
        self,
        publisher_id: UUID,
        command: PublisherReliabilityRecomputeCommand,
    ) -> PublisherReliabilitySnapshotView | None:
        now = datetime.now(UTC)
        start = now - timedelta(days=command.lookback_days)
        async with self._session_factory() as session, session.begin():
            publisher = await session.get(PublisherModel, publisher_id)
            if publisher is None:
                return None
            rows = list(
                (
                    await session.execute(
                        select(ArticleClaimModel, ClaimVerificationModel, ArticleModel)
                        .join(ArticleModel, ArticleClaimModel.article_id == ArticleModel.id)
                        .join(
                            ClaimVerificationModel,
    CanonicalEntityModel,
    EntityAliasModel,
                            ClaimVerificationModel.claim_id == ArticleClaimModel.id,
                        )
                        .where(
                            ArticleModel.publisher_id == publisher_id,
                            ClaimVerificationModel.created_at >= start,
                            ClaimVerificationModel.created_at <= now,
                        )
                        .order_by(ClaimVerificationModel.created_at)
                    )
                ).all()
            )
            latest: dict[UUID, tuple[ArticleClaimModel, ClaimVerificationModel, ArticleModel]] = {}
            for claim, verification, article in rows:
                latest[claim.id] = (claim, verification, article)
            observations: list[ReliabilityObservation] = []
            label_counts: Counter[str] = Counter()
            topic_counts: Counter[str] = Counter()
            for claim, verification, article in latest.values():
                claim_type = claim.extraction_features.get("claim_type")
                claim_type_value = str(claim_type) if claim_type else "other_factual"
                topic = classify_news_topic(f"{article.title} {claim.claim_text}")
                topic_counts[topic.topic_key] += 1
                if command.topic_key and topic.topic_key != command.topic_key:
                    continue
                label_counts[verification.label] += 1
                observations.append(
                    ReliabilityObservation(
                        label=verification.label,
                        confidence=verification.confidence_score,
                        claim_type=claim_type_value,
                        evidence_maturity=_evidence_maturity(verification),
                    )
                )
            topic_key = command.topic_key or "all"
            assessment = assess_publisher_reliability(
                tuple(observations),
                topic_key=topic_key,
                prior_alpha=command.prior_alpha,
                prior_beta=command.prior_beta,
            )
            model = PublisherReliabilitySnapshotModel(
                id=uuid7(),
                publisher_id=publisher_id,
                topic_key=topic_key,
                methodology_version=assessment.methodology_version,
                window_start=start,
                window_end=now,
                posterior_mean=assessment.posterior_mean,
                interval_low=assessment.interval_low,
                interval_high=assessment.interval_high,
                effective_successes=assessment.effective_successes,
                effective_failures=assessment.effective_failures,
                effective_sample_size=assessment.effective_sample_size,
                raw_observation_count=assessment.raw_observation_count,
                excluded_observation_count=assessment.excluded_observation_count,
                prior_alpha=assessment.prior_alpha,
                prior_beta=assessment.prior_beta,
                metadata_={
                    "label_counts": dict(sorted(label_counts.items())),
                    "topic_counts": dict(sorted(topic_counts.items())),
                    "topic_scope": (
                        "deterministic subject classification"
                        if command.topic_key
                        else "all subjects"
                    ),
                    "interpretation": assessment.interpretation,
                    "guardrail": (
                        "Reliability is scoped to verified claims, topic and time window; it "
                        "must not be presented as a permanent publisher truth/bias rating."
                    ),
                },
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _reliability_view(model, publisher.name)

    async def history(
        self,
        publisher_id: UUID,
        *,
        topic_key: str | None = None,
        limit: int = 50,
    ) -> list[PublisherReliabilitySnapshotView] | None:
        async with self._session_factory() as session:
            publisher = await session.get(PublisherModel, publisher_id)
            if publisher is None:
                return None
            statement = select(PublisherReliabilitySnapshotModel).where(
                PublisherReliabilitySnapshotModel.publisher_id == publisher_id
            )
            if topic_key:
                statement = statement.where(PublisherReliabilitySnapshotModel.topic_key == topic_key)
            rows = list(
                (
                    await session.scalars(
                        statement.order_by(PublisherReliabilitySnapshotModel.created_at.desc()).limit(
                            min(200, max(1, limit))
                        )
                    )
                ).all()
            )
            return [_reliability_view(item, publisher.name) for item in rows]


class TemporalKnowledgeGraphService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def rebuild(self, event_id: UUID) -> TemporalKnowledgeGraphView | None:
        async with self._session_factory() as session, session.begin():
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            claims = list(
                (
                    await session.scalars(
                        select(ArticleClaimModel)
                        .join(ArticleModel, ArticleClaimModel.article_id == ArticleModel.id)
                        .where(ArticleModel.event_id == event_id)
                        .order_by(ArticleClaimModel.created_at)
                    )
                ).all()
            )
            versions = {
                item.id: item
                for item in list(
                    (
                        await session.scalars(
                            select(ArticleVersionModel).where(
                                ArticleVersionModel.id.in_([claim.article_version_id for claim in claims])
                            )
                        )
                    ).all()
                )
            } if claims else {}
            commitments = list(
                (
                    await session.scalars(
                        select(EventCommitmentModel).where(EventCommitmentModel.event_id == event_id)
                    )
                ).all()
            )
            claim_ids = [item.id for item in claims]
            verifications = (
                list(
                    (
                        await session.scalars(
                            select(ClaimVerificationModel)
                            .where(ClaimVerificationModel.claim_id.in_(claim_ids))
                            .order_by(ClaimVerificationModel.created_at)
                        )
                    ).all()
                )
                if claim_ids
                else []
            )
            evidence_evaluations = (
                list(
                    (
                        await session.scalars(
                            select(EvidencePassageEvaluationModel)
                            .where(EvidencePassageEvaluationModel.claim_id.in_(claim_ids))
                            .order_by(EvidencePassageEvaluationModel.retrieved_at)
                        )
                    ).all()
                )
                if claim_ids
                else []
            )
            claim_inputs: list[KnowledgeClaimInput] = []
            for claim in claims:
                version = versions.get(claim.article_version_id)
                temporal = derive_temporal_context(
                    claim.claim_text,
                    published_at=version.published_at if version else None,
                    retrieved_at=version.retrieved_at if version else claim.created_at,
                )
                raw_entities = claim.extraction_features.get("entities")
                entities = tuple(str(item) for item in raw_entities) if isinstance(raw_entities, list) else ()
                attribution = claim.extraction_features.get("attribution")
                speaker = None
                if isinstance(attribution, dict) and isinstance(attribution.get("speaker"), str):
                    speaker = str(attribution["speaker"])
                claim_inputs.append(
                    KnowledgeClaimInput(
                        claim_id=str(claim.id),
                        claim_text=claim.claim_text,
                        observed_at=claim.created_at,
                        claim_type=(
                            str(claim.extraction_features.get("claim_type"))
                            if claim.extraction_features.get("claim_type")
                            else None
                        ),
                        entities=entities,
                        attribution_speaker=speaker,
                        valid_from=temporal.valid_from,
                        valid_to=None,
                    )
                )
            commitment_inputs = tuple(
                KnowledgeCommitmentInput(
                    commitment_id=str(item.id),
                    text=item.commitment_text,
                    commitment_type=item.commitment_type,
                    observed_at=item.first_observed_at,
                    actor=item.actor,
                    deadline_at=item.deadline_at,
                )
                for item in commitments
            )
            verification_inputs = tuple(
                KnowledgeVerificationInput(
                    verification_id=str(item.id),
                    claim_id=str(item.claim_id),
                    label=item.label,
                    confidence=item.confidence_score,
                    methodology_version=item.methodology_version,
                    observed_at=item.created_at,
                )
                for item in verifications
            )
            evidence_inputs = tuple(
                KnowledgeEvidenceInput(
                    evidence_id=str(item.id),
                    claim_id=str(item.claim_id),
                    source_url=item.source_url,
                    stance=item.stance,
                    evidence_class=item.evidence_class,
                    temporal_relation=item.temporal_relation,
                    primary_source=item.primary_source,
                    observed_at=item.retrieved_at,
                )
                for item in evidence_evaluations
            )
            entity_overrides = await _canonical_entity_overrides(session, claim_inputs)
            graph = build_event_knowledge_graph(
                event_id=str(event.id),
                event_title=event.title,
                event_observed_at=event.first_detected_at,
                claims=tuple(claim_inputs),
                commitments=commitment_inputs,
                verifications=verification_inputs,
                evidence=evidence_inputs,
                entity_key_overrides=entity_overrides,
            )
            now = datetime.now(UTC)
            existing_nodes = {
                item.node_key: item
                for item in list(
                    (
                        await session.scalars(
                            select(TemporalKnowledgeNodeModel).where(
                                TemporalKnowledgeNodeModel.event_id == event_id
                            )
                        )
                    ).all()
                )
            }
            existing_edges = {
                item.edge_key: item
                for item in list(
                    (
                        await session.scalars(
                            select(TemporalKnowledgeEdgeModel).where(
                                TemporalKnowledgeEdgeModel.event_id == event_id
                            )
                        )
                    ).all()
                )
            }
            for node in graph.nodes:
                model = existing_nodes.get(node.node_key)
                if model is None:
                    model = TemporalKnowledgeNodeModel(
                        id=uuid7(),
                        event_id=event_id,
                        node_key=node.node_key,
                        node_type=node.node_type,
                        label=node.label,
                        search_text=_node_search_text(node.label, node.payload),
                        observed_at=node.observed_at,
                        valid_from=node.valid_from,
                        valid_to=node.valid_to,
                        graph_version=graph.graph_version,
                        payload=node.payload,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(model)
                else:
                    model.label = node.label
                    model.search_text = _node_search_text(node.label, node.payload)
                    model.valid_from = node.valid_from
                    model.valid_to = node.valid_to
                    model.graph_version = graph.graph_version
                    model.payload = node.payload
                    model.updated_at = now
            for edge in graph.edges:
                model = existing_edges.get(edge.edge_key)
                if model is None:
                    model = TemporalKnowledgeEdgeModel(
                        id=uuid7(),
                        event_id=event_id,
                        edge_key=edge.edge_key,
                        source_key=edge.source_key,
                        target_key=edge.target_key,
                        relation=edge.relation,
                        observed_at=edge.observed_at,
                        valid_from=edge.valid_from,
                        valid_to=edge.valid_to,
                        graph_version=graph.graph_version,
                        payload=edge.payload,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(model)
                else:
                    model.valid_from = edge.valid_from
                    model.valid_to = edge.valid_to
                    model.graph_version = graph.graph_version
                    model.payload = edge.payload
                    model.updated_at = now
            await session.flush()
        return await self.get(event_id)

    async def get(
        self,
        event_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> TemporalKnowledgeGraphView | None:
        as_of = _utc(as_of)
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            nodes = list(
                (
                    await session.scalars(
                        select(TemporalKnowledgeNodeModel)
                        .where(TemporalKnowledgeNodeModel.event_id == event_id)
                        .order_by(TemporalKnowledgeNodeModel.node_type, TemporalKnowledgeNodeModel.label)
                    )
                ).all()
            )
            edges = list(
                (
                    await session.scalars(
                        select(TemporalKnowledgeEdgeModel)
                        .where(TemporalKnowledgeEdgeModel.event_id == event_id)
                        .order_by(TemporalKnowledgeEdgeModel.relation)
                    )
                ).all()
            )
        if as_of is not None:
            nodes = [item for item in nodes if _visible_as_of(item, as_of)]
            visible_keys = {item.node_key for item in nodes}
            edges = [
                item
                for item in edges
                if item.source_key in visible_keys
                and item.target_key in visible_keys
                and _visible_as_of(item, as_of)
            ]
        graph_version = (
            nodes[0].graph_version if nodes else "temporal-event-knowledge-graph-v1"
        )
        return TemporalKnowledgeGraphView(
            event_id=event_id,
            event_title=event.title,
            graph_version=graph_version,
            as_of=as_of,
            node_count=len(nodes),
            edge_count=len(edges),
            nodes=[_node_view(item) for item in nodes],
            edges=[_edge_view(item) for item in edges],
            generated_at=datetime.now(UTC),
            interpretation=(
                "The graph is provenance-oriented and temporal. Nodes/edges are visible only "
                "after observation and within explicit validity windows; graph presence is not "
                "itself proof that a claim is true."
            ),
        )


    async def diff(
        self,
        event_id: UUID,
        *,
        from_at: datetime,
        to_at: datetime,
    ) -> TemporalKnowledgeGraphDiffView | None:
        start = _utc(from_at)
        end = _utc(to_at)
        if start is None or end is None:
            raise ValueError("from_at and to_at are required")
        if end <= start:
            raise ValueError("to_at must be later than from_at")
        before = await self.get(event_id, as_of=start)
        after = await self.get(event_id, as_of=end)
        if before is None or after is None:
            return None
        before_nodes = {item.node_key: item for item in before.nodes}
        after_nodes = {item.node_key: item for item in after.nodes}
        before_edges = {item.edge_key: item for item in before.edges}
        after_edges = {item.edge_key: item for item in after.edges}
        added_nodes = [after_nodes[key] for key in sorted(after_nodes.keys() - before_nodes.keys())]
        expired_nodes = [before_nodes[key] for key in sorted(before_nodes.keys() - after_nodes.keys())]
        added_edges = [after_edges[key] for key in sorted(after_edges.keys() - before_edges.keys())]
        expired_edges = [before_edges[key] for key in sorted(before_edges.keys() - after_edges.keys())]
        return TemporalKnowledgeGraphDiffView(
            event_id=event_id,
            from_at=start,
            to_at=end,
            added_nodes=added_nodes,
            expired_nodes=expired_nodes,
            added_edges=added_edges,
            expired_edges=expired_edges,
            summary={
                "added_nodes": len(added_nodes),
                "expired_nodes": len(expired_nodes),
                "added_edges": len(added_edges),
                "expired_edges": len(expired_edges),
            },
            generated_at=datetime.now(UTC),
            interpretation=(
                "This is an as-known-then graph difference between two observation times. "
                "Added verification/evidence nodes represent newly observed knowledge, not a "
                "rewrite of the earlier state."
            ),
        )


async def _canonical_entity_overrides(
    session: AsyncSession,
    claims: list[KnowledgeClaimInput],
) -> dict[str, str]:
    raw_entities = {
        " ".join(entity.split()).strip()
        for claim in claims
        for entity in claim.entities
        if " ".join(entity.split()).strip()
    }
    if not raw_entities:
        return {}
    normalized_targets = {normalize_entity_name(value): value for value in raw_entities}
    models = list((await session.scalars(select(CanonicalEntityModel))).all())
    if not models:
        return {}
    aliases = list(
        (
            await session.scalars(
                select(EntityAliasModel).where(
                    EntityAliasModel.entity_id.in_([item.id for item in models])
                )
            )
        ).all()
    )
    values_by_normalized: dict[str, set[str]] = {}
    for item in models:
        values_by_normalized.setdefault(item.normalized_name, set()).add(item.entity_key)
    key_by_id = {item.id: item.entity_key for item in models}
    for alias in aliases:
        key = key_by_id.get(alias.entity_id)
        if key:
            values_by_normalized.setdefault(alias.normalized_alias, set()).add(key)
    overrides: dict[str, str] = {}
    for normalized, raw in normalized_targets.items():
        matches = values_by_normalized.get(normalized, set())
        if len(matches) == 1:
            overrides[raw] = next(iter(matches))
    return overrides


def _attempt_view(item: EvidenceRetrievalAttemptModel) -> EvidenceRetrievalAttemptView:
    return EvidenceRetrievalAttemptView(
        id=item.id,
        search_run_id=item.search_run_id,
        authority_profile_id=item.authority_profile_id,
        search_url=item.search_url,
        candidate_url=item.candidate_url,
        status=item.status,
        http_status=item.http_status,
        body_sha256=item.body_sha256,
        error_type=item.error_type,
        error_message=item.error_message,
        metadata=item.metadata_,
        created_at=item.created_at,
    )


def _evidence_maturity(item: ClaimVerificationModel) -> float:
    factors = item.confidence_factors or {}
    lineage_count = factors.get("independent_lineage_count")
    primary = bool(
        factors.get("primary_support_present") or factors.get("primary_contradiction_present")
    )
    complete = bool(factors.get("retrieval_complete"))
    score = 0.55
    if isinstance(lineage_count, int | float):
        score += min(0.2, 0.08 * float(lineage_count))
    if primary:
        score += 0.15
    if complete:
        score += 0.1
    return min(1.0, score)


def _reliability_view(
    item: PublisherReliabilitySnapshotModel,
    publisher_name: str,
) -> PublisherReliabilitySnapshotView:
    return PublisherReliabilitySnapshotView(
        id=item.id,
        publisher_id=item.publisher_id,
        publisher_name=publisher_name,
        topic_key=item.topic_key,
        methodology_version=item.methodology_version,
        window_start=item.window_start,
        window_end=item.window_end,
        posterior_mean=item.posterior_mean,
        interval_low=item.interval_low,
        interval_high=item.interval_high,
        effective_successes=item.effective_successes,
        effective_failures=item.effective_failures,
        effective_sample_size=item.effective_sample_size,
        raw_observation_count=item.raw_observation_count,
        excluded_observation_count=item.excluded_observation_count,
        prior_alpha=item.prior_alpha,
        prior_beta=item.prior_beta,
        interpretation=str(item.metadata_.get("interpretation") or ""),
        metadata=item.metadata_,
        created_at=item.created_at,
    )


def _node_view(item: TemporalKnowledgeNodeModel) -> TemporalKnowledgeNodeView:
    return TemporalKnowledgeNodeView(
        node_key=item.node_key,
        node_type=item.node_type,
        label=item.label,
        observed_at=item.observed_at,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        payload=item.payload,
    )


def _edge_view(item: TemporalKnowledgeEdgeModel) -> TemporalKnowledgeEdgeView:
    return TemporalKnowledgeEdgeView(
        edge_key=item.edge_key,
        source_key=item.source_key,
        target_key=item.target_key,
        relation=item.relation,
        observed_at=item.observed_at,
        valid_from=item.valid_from,
        valid_to=item.valid_to,
        payload=item.payload,
    )


def _visible_as_of(item, as_of: datetime) -> bool:
    if item.observed_at > as_of:
        return False
    if item.valid_from is not None and item.valid_from > as_of:
        return False
    if item.valid_to is not None and as_of > item.valid_to:
        return False
    return True


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _node_search_text(label: str, payload: dict[str, object]) -> str:
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return " ".join(f"{label} {payload_text}".split())[:20_000]
