from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from dateutil import parser as date_parser
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.evidence.authority_search import AuthoritySearchSpec
from newsintel.application.articles.verification_service import ClaimVerificationService
from newsintel.application.intelligence.dto import (
    ClaimConfidenceHistoryView,
    ClaimConfidenceSnapshotView,
    CommitmentDiscoveryView,
    CommitmentEvaluationExecutionView,
    CommitmentOutcomeView,
    CommitmentView,
    EvidenceEvaluationCommand,
    EvidenceEvaluationExecutionView,
    EvidenceAuthorityCreateCommand,
    EvidenceAuthorityView,
    EvidenceHistoryView,
    EvidencePassageEvaluationView,
    EvidencePlanExecutionView,
    EvidenceRetrievalAttemptView,
    EvidencePlanView,
    EvidenceRequirementView,
    EvidenceSearchCompleteView,
    EvidenceSearchRunView,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.authority import (
    authority_matches_source,
    normalize_domains,
    normalized_host,
)
from newsintel.domain.intelligence.circularity import detect_circular_sourcing
from newsintel.domain.intelligence.lineage import (
    estimate_lineage_similarity,
    fingerprint_content,
    fingerprint_from_metadata,
    fingerprint_metadata,
    independence_cap_from_lineage_similarity,
)
from newsintel.domain.intelligence.ownership import (
    OwnershipMembership,
    OwnershipRelationship,
    ownership_independence_cap,
)
from newsintel.domain.intelligence.outcomes import (
    OutcomeStatus,
    assess_outcome,
    extract_trackable_commitment,
)
from newsintel.domain.intelligence.primary_evidence import plan_primary_evidence
from newsintel.domain.intelligence.stance import PassageStance, assess_evidence_stance
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleModel,
    ArticleVersionModel,
    ClaimEvidenceLinkModel,
    ClaimVerificationModel,
    CommitmentOutcomeModel,
    EventCommitmentModel,
    EventModel,
    PublisherDomainModel,
    PublisherModel,
    PublisherOwnershipMembershipModel,
    EvidenceAuthorityProfileModel,
    EvidencePassageEvaluationModel,
    EvidenceRetrievalAttemptModel,
    EvidenceSearchRunModel,
)


class EvidenceIntelligenceService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_authority(
        self,
        command: EvidenceAuthorityCreateCommand,
    ) -> EvidenceAuthorityView:
        now = datetime.now(UTC)
        base_url = str(command.base_url)
        base_host = normalized_host(base_url)
        allowed = normalize_domains(command.allowed_domains or ([base_host] if base_host else []))
        if base_host and base_host not in allowed:
            allowed.insert(0, base_host)
        if command.search_url_template:
            AuthoritySearchSpec(
                authority_id="validation",
                name=command.name,
                evidence_class=command.evidence_class.value,
                base_url=base_url,
                allowed_domains=tuple(allowed),
                search_url_template=command.search_url_template,
                adapter_type=command.adapter_type,
                adapter_config=command.adapter_config,
            )
        async with self._session_factory() as session, session.begin():
            model = EvidenceAuthorityProfileModel(
                id=uuid7(),
                name=command.name,
                evidence_class=command.evidence_class.value,
                jurisdiction=command.jurisdiction,
                language=command.language,
                base_url=base_url,
                allowed_domains=allowed,
                search_url_template=command.search_url_template,
                adapter_type=command.adapter_type.value,
                adapter_config=command.adapter_config,
                trust_scope=command.trust_scope,
                active=True,
                metadata_={
                    "provenance": "administrator_configured",
                    "guardrail": "Authority status applies only to the configured evidence class and domains.",
                },
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            await session.flush()
            return _authority_view(model)

    async def list_authorities(
        self,
        *,
        evidence_class: str | None = None,
    ) -> list[EvidenceAuthorityView]:
        async with self._session_factory() as session:
            statement = select(EvidenceAuthorityProfileModel).where(
                EvidenceAuthorityProfileModel.active.is_(True)
            )
            if evidence_class:
                statement = statement.where(
                    EvidenceAuthorityProfileModel.evidence_class == evidence_class
                )
            rows = list((await session.scalars(statement.order_by(EvidenceAuthorityProfileModel.name))).all())
            return [_authority_view(item) for item in rows]

    async def create_plan(self, claim_id: UUID) -> EvidencePlanExecutionView | None:
        async with self._session_factory() as session, session.begin():
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            plan = plan_primary_evidence(
                claim.claim_text,
                extraction_features=claim.extraction_features,
            )
            now = datetime.now(UTC)
            requirement_classes = [item.evidence_class.value for item in plan.requirements]
            authorities = list(
                (
                    await session.scalars(
                        select(EvidenceAuthorityProfileModel).where(
                            EvidenceAuthorityProfileModel.active.is_(True),
                            EvidenceAuthorityProfileModel.evidence_class.in_(requirement_classes),
                        )
                    )
                ).all()
            )
            plan_payload = _plan_dict(plan, authorities=authorities)
            run = EvidenceSearchRunModel(
                id=uuid7(),
                claim_id=claim_id,
                plan_key=plan.plan_key,
                planner_version=plan.planner_version,
                status="planned",
                plan=plan_payload,
                retrieval_complete=False,
                source_count=0,
                evidence_count=0,
                started_at=now,
                completed_at=None,
                metadata_={
                    "guardrail": "Plan creation does not assert that any listed evidence exists.",
                },
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            await session.flush()
            return EvidencePlanExecutionView(
                claim_id=claim_id,
                run=_run_view(run),
                plan=_plan_view(plan, authorities=authorities),
            )

    async def evaluate_evidence(
        self,
        claim_id: UUID,
        command: EvidenceEvaluationCommand,
    ) -> EvidenceEvaluationExecutionView | None:
        async with self._session_factory() as session, session.begin():
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            version = await session.get(ArticleVersionModel, claim.article_version_id)
            run = None
            if command.search_run_id is not None:
                run = await session.get(EvidenceSearchRunModel, command.search_run_id)
                if run is None or run.claim_id != claim_id:
                    raise ValueError("search_run_id does not belong to this claim")
            retrieved_at = _utc(command.retrieved_at) or datetime.now(UTC)
            assessment = assess_evidence_stance(
                claim.claim_text,
                command.evidence_text,
                claim_published_at=version.published_at if version else None,
                evidence_published_at=_utc(command.published_at),
                evidence_retrieved_at=retrieved_at,
            )
            passage = assessment.best_passage
            passage_text = passage.text if passage is not None else _fallback_passage(command.evidence_text)
            passage_hash = sha256(passage_text.encode("utf-8")).hexdigest()
            source_url = str(command.source_url)
            existing_evaluations = list(
                (
                    await session.scalars(
                        select(EvidencePassageEvaluationModel).where(
                            EvidencePassageEvaluationModel.claim_id == claim_id
                        )
                    )
                ).all()
            )
            existing = next(
                (
                    item
                    for item in existing_evaluations
                    if item.source_url == source_url and item.passage_sha256 == passage_hash
                ),
                None,
            )
            if existing is not None:
                return EvidenceEvaluationExecutionView(
                    claim_id=claim_id,
                    evaluation=_evaluation_view(existing),
                    evidence_link_id=None,
                )
            evidence_class = command.evidence_class.value if command.evidence_class is not None else None
            authority_match = await _matching_authority(
                session,
                source_url=source_url,
                evidence_class=evidence_class,
            )
            primary_source = command.primary_source and authority_match is not None
            content_lineage = fingerprint_content(command.evidence_text)
            max_lineage_similarity = 0.0
            for prior in existing_evaluations:
                prior_lineage = fingerprint_from_metadata(prior.metadata_.get("content_lineage"))
                if prior_lineage is None:
                    continue
                max_lineage_similarity = max(
                    max_lineage_similarity,
                    estimate_lineage_similarity(content_lineage, prior_lineage),
                )
            requested_independence = command.independence_score
            effective_independence = min(
                requested_independence,
                independence_cap_from_lineage_similarity(max_lineage_similarity),
            )
            source_host = normalized_host(source_url)
            origin_article = await session.get(ArticleModel, claim.article_id)
            origin_publisher = (
                await session.get(PublisherModel, origin_article.publisher_id)
                if origin_article is not None
                else None
            )
            evidence_publisher_id = await _publisher_id_for_source(session, source_host)
            ownership_assessment = None
            source_relationship = None
            if origin_article is not None and evidence_publisher_id is not None:
                if evidence_publisher_id == origin_article.publisher_id:
                    effective_independence = min(effective_independence, 0.1)
                    source_relationship = "same_publisher"
                else:
                    origin_memberships = await _ownership_memberships(
                        session, origin_article.publisher_id, retrieved_at
                    )
                    evidence_memberships = await _ownership_memberships(
                        session, evidence_publisher_id, retrieved_at
                    )
                    ownership_assessment = ownership_independence_cap(
                        origin_memberships, evidence_memberships, observed_at=retrieved_at
                    )
                    effective_independence = min(
                        effective_independence, ownership_assessment.independence_cap
                    )
                    if ownership_assessment.same_group:
                        source_relationship = ownership_assessment.relationship
            circularity = detect_circular_sourcing(
                command.evidence_text,
                origin_publisher_name=origin_publisher.name if origin_publisher else None,
                origin_domain=origin_publisher.canonical_domain if origin_publisher else None,
            )
            effective_independence = min(
                effective_independence, circularity.independence_cap
            )
            if not primary_source and source_host and any(
                normalized_host(item.source_url) == source_host for item in existing_evaluations
            ):
                effective_independence = min(effective_independence, 0.5)
            lineage_key = (
                f"authority:{authority_match.id}"
                if authority_match is not None
                else f"publisher:{evidence_publisher_id}" if evidence_publisher_id is not None
                else f"domain:{source_host}" if source_host else f"url:{source_url}"
            )
            evaluation = EvidencePassageEvaluationModel(
                id=uuid7(),
                claim_id=claim_id,
                search_run_id=run.id if run else None,
                source_url=source_url,
                source_type=command.source_type,
                evidence_class=evidence_class,
                passage_text=passage_text,
                passage_sha256=passage_hash,
                stance=assessment.stance.value,
                stance_confidence=assessment.confidence,
                assessor_version=assessment.assessor_version,
                temporal_relation=assessment.temporal_relation.value,
                published_at=_utc(command.published_at),
                retrieved_at=retrieved_at,
                independence_score=effective_independence,
                primary_source=primary_source,
                metadata_={
                    **assessment.metadata,
                    "rationale": assessment.rationale,
                    "similarity_score": passage.similarity_score if passage else None,
                    "lexical_overlap": passage.lexical_overlap if passage else None,
                    "passage_relationship": passage.relationship.value if passage else None,
                    "authority_profile_id": str(authority_match.id) if authority_match else None,
                    "authority_profile_name": authority_match.name if authority_match else None,
                    "primary_source_asserted_by_analyst": command.primary_source,
                    "primary_source_validated_by_registry": primary_source,
                    "content_lineage": fingerprint_metadata(content_lineage),
                    "max_prior_lineage_similarity": round(max_lineage_similarity, 4),
                    "requested_independence_score": requested_independence,
                    "effective_independence_score": effective_independence,
                    "lineage_key": lineage_key,
                    "evidence_publisher_id": str(evidence_publisher_id) if evidence_publisher_id else None,
                    "source_relationship": source_relationship,
                    "ownership_independence_cap": (
                        ownership_assessment.independence_cap if ownership_assessment else None
                    ),
                    "shared_ownership_group": (
                        ownership_assessment.same_group if ownership_assessment else False
                    ),
                    "circular_sourcing_detected": circularity.detected,
                    "circular_sourcing_reference": circularity.matched_reference,
                    "guardrail": "Passage stance is evidence comparison, not an automatic factual-truth label.",
                },
                created_at=retrieved_at,
            )
            session.add(evaluation)
            link_id = None
            if passage is not None and assessment.stance is not PassageStance.INSUFFICIENT:
                link_id = uuid7()
                session.add(
                    ClaimEvidenceLinkModel(
                        id=link_id,
                        claim_id=claim_id,
                        evidence_article_id=None,
                        evidence_article_version_id=None,
                        source_url=source_url,
                        source_type=command.source_type,
                        relationship=_link_relationship(assessment.stance),
                        retrieved_at=retrieved_at,
                        similarity_score=passage.similarity_score,
                        independence_score=effective_independence,
                        metadata_={
                            "evidence_evaluation_id": str(evaluation.id),
                            "evidence_class": evidence_class,
                            "primary_source": primary_source,
                            "primary_source_asserted_by_analyst": command.primary_source,
                            "primary_source_validated_by_registry": primary_source,
                            "authority_profile_id": str(authority_match.id) if authority_match else None,
                            "evidence_quality": assessment.confidence,
                            "lineage_key": lineage_key,
                            "evidence_publisher_id": str(evidence_publisher_id) if evidence_publisher_id else None,
                            "source_relationship": source_relationship,
                            "ownership_independence_cap": (
                                ownership_assessment.independence_cap if ownership_assessment else None
                            ),
                            "shared_ownership_group": (
                                ownership_assessment.same_group if ownership_assessment else False
                            ),
                            "circular_sourcing_detected": circularity.detected,
                            "circular_sourcing_reference": circularity.matched_reference,
                            "max_prior_lineage_similarity": round(max_lineage_similarity, 4),
                            "requested_independence_score": requested_independence,
                            "effective_independence_score": effective_independence,
                            "passage_sha256": passage_hash,
                            "passage_text": passage_text,
                            "temporal_relation": assessment.temporal_relation.value,
                            "raw_stance": assessment.stance.value,
                        },
                        created_at=retrieved_at,
                    )
                )
            await session.flush()
            if run is not None:
                run.status = "in_progress"
                run.updated_at = retrieved_at
                run.evidence_count = int(
                    await session.scalar(
                        select(func.count(EvidencePassageEvaluationModel.id)).where(
                            EvidencePassageEvaluationModel.search_run_id == run.id
                        )
                    )
                    or 0
                )
                run.source_count = int(
                    await session.scalar(
                        select(func.count(func.distinct(EvidencePassageEvaluationModel.source_url))).where(
                            EvidencePassageEvaluationModel.search_run_id == run.id
                        )
                    )
                    or 0
                )
            return EvidenceEvaluationExecutionView(
                claim_id=claim_id,
                evaluation=_evaluation_view(evaluation),
                evidence_link_id=link_id,
            )

    async def complete_search(
        self,
        claim_id: UUID,
        run_id: UUID,
    ) -> EvidenceSearchCompleteView | None:
        async with self._session_factory() as session, session.begin():
            claim = await session.get(ArticleClaimModel, claim_id)
            run = await session.get(EvidenceSearchRunModel, run_id)
            if claim is None or run is None or run.claim_id != claim_id:
                return None
            now = datetime.now(UTC)
            run.status = "completed"
            run.retrieval_complete = True
            run.completed_at = now
            run.updated_at = now
            await session.flush()
            run_view = _run_view(run)
        verification = await ClaimVerificationService(self._session_factory).recompute(
            claim_id,
            retrieval_complete=True,
        )
        return EvidenceSearchCompleteView(
            claim_id=claim_id,
            run=run_view,
            verification_label=(verification.verification.label if verification else None),
            verification_confidence=(
                verification.verification.confidence_score if verification else None
            ),
            verification_id=(verification.verification.id if verification else None),
        )

    async def history(self, claim_id: UUID) -> EvidenceHistoryView | None:
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            runs = list(
                (
                    await session.scalars(
                        select(EvidenceSearchRunModel)
                        .where(EvidenceSearchRunModel.claim_id == claim_id)
                        .order_by(EvidenceSearchRunModel.created_at)
                    )
                ).all()
            )
            evaluations = list(
                (
                    await session.scalars(
                        select(EvidencePassageEvaluationModel)
                        .where(EvidencePassageEvaluationModel.claim_id == claim_id)
                        .order_by(EvidencePassageEvaluationModel.retrieved_at)
                    )
                ).all()
            )
            run_ids = [item.id for item in runs]
            attempts = (
                list(
                    (
                        await session.scalars(
                            select(EvidenceRetrievalAttemptModel)
                            .where(EvidenceRetrievalAttemptModel.search_run_id.in_(run_ids))
                            .order_by(EvidenceRetrievalAttemptModel.created_at)
                        )
                    ).all()
                )
                if run_ids
                else []
            )
            confidence = await _confidence_history(session, claim)
            return EvidenceHistoryView(
                claim_id=claim_id,
                runs=[_run_view(item) for item in runs],
                evaluations=[_evaluation_view(item) for item in evaluations],
                retrieval_attempts=[_retrieval_attempt_view(item) for item in attempts],
                confidence_history=confidence,
            )

    async def confidence_history(self, claim_id: UUID) -> ClaimConfidenceHistoryView | None:
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            return await _confidence_history(session, claim)


class CommitmentTrackingService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def discover(self, event_id: UUID) -> CommitmentDiscoveryView | None:
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
            existing = list(
                (
                    await session.scalars(
                        select(EventCommitmentModel).where(EventCommitmentModel.event_id == event_id)
                    )
                ).all()
            )
            by_key = {item.commitment_key: item for item in existing}
            discovered = 0
            now = datetime.now(UTC)
            for claim in claims:
                attribution = claim.extraction_features.get("attribution")
                item = extract_trackable_commitment(
                    claim.claim_text,
                    attribution=attribution if isinstance(attribution, dict) else None,
                )
                if item is None or item.commitment_key in by_key:
                    continue
                model = EventCommitmentModel(
                    id=uuid7(),
                    event_id=event_id,
                    source_claim_id=claim.id,
                    commitment_key=item.commitment_key,
                    commitment_type=item.commitment_type.value,
                    commitment_text=item.text,
                    actor=item.actor,
                    deadline_text=item.deadline_text,
                    deadline_at=_parse_deadline(item.deadline_text),
                    status=OutcomeStatus.PENDING.value,
                    first_observed_at=claim.created_at,
                    last_evaluated_at=None,
                    metadata_={
                        "tracker_version": "commitment-outcome-tracker-v1",
                        "temporal_references": list(item.temporal_references),
                    },
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                by_key[item.commitment_key] = model
                discovered += 1
            await session.flush()
            values = sorted(by_key.values(), key=lambda item: item.first_observed_at)
            return CommitmentDiscoveryView(
                event_id=event_id,
                discovered_count=discovered,
                total_count=len(values),
                commitments=[_commitment_view(item) for item in values],
            )

    async def list_for_event(self, event_id: UUID) -> list[CommitmentView] | None:
        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(EventCommitmentModel)
                        .where(EventCommitmentModel.event_id == event_id)
                        .order_by(EventCommitmentModel.first_observed_at)
                    )
                ).all()
            )
            return [_commitment_view(item) for item in rows]

    async def evaluate(
        self,
        commitment_id: UUID,
        *,
        evidence_url: str,
        evidence_text: str,
        source_claim_id: UUID | None = None,
        observed_at: datetime | None = None,
    ) -> CommitmentEvaluationExecutionView | None:
        async with self._session_factory() as session, session.begin():
            commitment = await session.get(EventCommitmentModel, commitment_id)
            if commitment is None:
                return None
            observed = _utc(observed_at) or datetime.now(UTC)
            assessment = assess_outcome(
                commitment.commitment_text,
                evidence_text,
                deadline_at=commitment.deadline_at,
                observed_at=observed,
            )
            model = CommitmentOutcomeModel(
                id=uuid7(),
                commitment_id=commitment_id,
                source_claim_id=source_claim_id,
                evidence_url=evidence_url,
                status=assessment.status.value,
                confidence=assessment.confidence,
                tracker_version=assessment.tracker_version,
                observed_at=observed,
                reasoning=assessment.rationale,
                metadata_={
                    "matched_markers": list(assessment.matched_markers),
                    "guardrail": "Outcome status is evidence-scoped; silence does not imply fulfillment or failure.",
                },
                created_at=observed,
            )
            session.add(model)
            if assessment.status not in {OutcomeStatus.UNKNOWN, OutcomeStatus.PENDING}:
                commitment.status = assessment.status.value
            commitment.last_evaluated_at = observed
            commitment.updated_at = observed
            await session.flush()
            return CommitmentEvaluationExecutionView(
                commitment=_commitment_view(commitment),
                outcome=_outcome_view(model),
            )


def _plan_dict(plan, *, authorities: list[EvidenceAuthorityProfileModel] | None = None) -> dict[str, object]:
    return {
        "planner_version": plan.planner_version,
        "claim_type": plan.claim_type,
        "claim_text": plan.claim_text,
        "plan_key": plan.plan_key,
        "requirements": [asdict(item) for item in plan.requirements],
        "search_terms": list(plan.search_terms),
        "completeness_criteria": plan.completeness_criteria,
        "configured_authorities": [_authority_summary(item) for item in (authorities or [])],
    }


def _plan_view(
    plan,
    *,
    authorities: list[EvidenceAuthorityProfileModel] | None = None,
) -> EvidencePlanView:
    return EvidencePlanView(
        planner_version=plan.planner_version,
        claim_type=plan.claim_type,
        claim_text=plan.claim_text,
        plan_key=plan.plan_key,
        requirements=[
            EvidenceRequirementView(
                evidence_class=item.evidence_class.value,
                priority=item.priority,
                required=item.required,
                rationale=item.rationale,
                query_hints=list(item.query_hints),
                authority_hints=list(item.authority_hints),
            )
            for item in plan.requirements
        ],
        search_terms=list(plan.search_terms),
        completeness_criteria=plan.completeness_criteria,
        configured_authorities=[_authority_summary(item) for item in (authorities or [])],
    )


def _run_view(run: EvidenceSearchRunModel) -> EvidenceSearchRunView:
    return EvidenceSearchRunView(
        id=run.id,
        claim_id=run.claim_id,
        status=run.status,
        plan_key=run.plan_key,
        planner_version=run.planner_version,
        retrieval_complete=run.retrieval_complete,
        source_count=run.source_count,
        evidence_count=run.evidence_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
        plan=run.plan,
        metadata=run.metadata_,
    )


def _evaluation_view(item: EvidencePassageEvaluationModel) -> EvidencePassageEvaluationView:
    return EvidencePassageEvaluationView(
        id=item.id,
        claim_id=item.claim_id,
        search_run_id=item.search_run_id,
        source_url=item.source_url,
        source_type=item.source_type,
        evidence_class=item.evidence_class,
        passage_text=item.passage_text,
        passage_sha256=item.passage_sha256,
        stance=item.stance,
        stance_confidence=item.stance_confidence,
        assessor_version=item.assessor_version,
        temporal_relation=item.temporal_relation,
        published_at=item.published_at,
        retrieved_at=item.retrieved_at,
        independence_score=item.independence_score,
        primary_source=item.primary_source,
        metadata=item.metadata_,
        created_at=item.created_at,
    )


def _retrieval_attempt_view(item: EvidenceRetrievalAttemptModel) -> EvidenceRetrievalAttemptView:
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


async def _confidence_history(
    session: AsyncSession,
    claim: ArticleClaimModel,
) -> ClaimConfidenceHistoryView:
    rows = list(
        (
            await session.scalars(
                select(ClaimVerificationModel)
                .where(ClaimVerificationModel.claim_id == claim.id)
                .order_by(ClaimVerificationModel.created_at)
            )
        ).all()
    )
    snapshots = [
        ClaimConfidenceSnapshotView(
            verification_id=item.id,
            label=item.label,
            confidence_score=item.confidence_score,
            methodology_version=item.methodology_version,
            created_at=item.created_at,
            confidence_factors=item.confidence_factors,
            reasoning_trace=item.reasoning_trace,
        )
        for item in rows
    ]
    latest = rows[-1] if rows else None
    return ClaimConfidenceHistoryView(
        claim_id=claim.id,
        claim_text=claim.claim_text,
        current_label=latest.label if latest else None,
        current_confidence=latest.confidence_score if latest else None,
        snapshots=snapshots,
        generated_at=datetime.now(UTC),
        interpretation=(
            "Each snapshot is the platform's evidence state at that recorded time. Later "
            "evidence may change the current assessment without rewriting earlier snapshots."
        ),
    )


def _commitment_view(item: EventCommitmentModel) -> CommitmentView:
    return CommitmentView(
        id=item.id,
        event_id=item.event_id,
        source_claim_id=item.source_claim_id,
        commitment_key=item.commitment_key,
        commitment_type=item.commitment_type,
        commitment_text=item.commitment_text,
        actor=item.actor,
        deadline_text=item.deadline_text,
        deadline_at=item.deadline_at,
        status=item.status,
        first_observed_at=item.first_observed_at,
        last_evaluated_at=item.last_evaluated_at,
        metadata=item.metadata_,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _outcome_view(item: CommitmentOutcomeModel) -> CommitmentOutcomeView:
    return CommitmentOutcomeView(
        id=item.id,
        commitment_id=item.commitment_id,
        source_claim_id=item.source_claim_id,
        evidence_url=item.evidence_url,
        status=item.status,
        confidence=item.confidence,
        tracker_version=item.tracker_version,
        observed_at=item.observed_at,
        reasoning=item.reasoning,
        metadata=item.metadata_,
        created_at=item.created_at,
    )


def _authority_summary(item: EvidenceAuthorityProfileModel) -> dict[str, object]:
    return {
        "id": str(item.id),
        "name": item.name,
        "evidence_class": item.evidence_class,
        "jurisdiction": item.jurisdiction,
        "language": item.language,
        "base_url": item.base_url,
        "allowed_domains": list(item.allowed_domains),
        "search_url_template": item.search_url_template,
        "adapter_type": item.adapter_type,
        "adapter_config": item.adapter_config,
        "trust_scope": item.trust_scope,
    }


def _authority_view(item: EvidenceAuthorityProfileModel) -> EvidenceAuthorityView:
    return EvidenceAuthorityView(
        id=item.id,
        name=item.name,
        evidence_class=item.evidence_class,
        jurisdiction=item.jurisdiction,
        language=item.language,
        base_url=item.base_url,
        allowed_domains=list(item.allowed_domains),
        search_url_template=item.search_url_template,
        adapter_type=item.adapter_type,
        adapter_config=item.adapter_config,
        trust_scope=item.trust_scope,
        active=item.active,
        metadata=item.metadata_,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _publisher_id_for_source(
    session: AsyncSession,
    host: str | None,
) -> UUID | None:
    if not host:
        return None
    domain = await session.scalar(
        select(PublisherDomainModel).where(
            PublisherDomainModel.domain == host,
            PublisherDomainModel.active.is_(True),
        )
    )
    if domain is not None:
        return domain.publisher_id
    publisher = await session.scalar(
        select(PublisherModel).where(PublisherModel.canonical_domain == host)
    )
    return publisher.id if publisher is not None else None


async def _ownership_memberships(
    session: AsyncSession,
    publisher_id: UUID,
    observed_at: datetime,
) -> tuple[OwnershipMembership, ...]:
    rows = list(
        (
            await session.scalars(
                select(PublisherOwnershipMembershipModel).where(
                    PublisherOwnershipMembershipModel.publisher_id == publisher_id
                )
            )
        ).all()
    )
    result: list[OwnershipMembership] = []
    for item in rows:
        try:
            relationship = OwnershipRelationship(item.relationship)
        except ValueError:
            relationship = OwnershipRelationship.UNKNOWN
        result.append(
            OwnershipMembership(
                publisher_id=str(item.publisher_id),
                group_id=str(item.group_id),
                relationship=relationship,
                ownership_fraction=item.ownership_fraction,
                valid_from=item.valid_from,
                valid_to=item.valid_to,
            )
        )
    return tuple(result)


async def _matching_authority(
    session: AsyncSession,
    *,
    source_url: str,
    evidence_class: str | None,
) -> EvidenceAuthorityProfileModel | None:
    if not evidence_class:
        return None
    rows = list(
        (
            await session.scalars(
                select(EvidenceAuthorityProfileModel).where(
                    EvidenceAuthorityProfileModel.active.is_(True),
                    EvidenceAuthorityProfileModel.evidence_class == evidence_class,
                )
            )
        ).all()
    )
    for item in rows:
        if authority_matches_source(source_url=source_url, allowed_domains=item.allowed_domains):
            return item
    return None


def _link_relationship(stance: PassageStance) -> str:
    if stance is PassageStance.SUPPORT:
        return "support"
    if stance is PassageStance.CONTRADICT:
        return "contradict"
    if stance is PassageStance.DISPUTE:
        return "dispute"
    return "context"


def _is_primary_class(value: str | None) -> bool:
    if not value:
        return False
    return value not in {"independent_reporting", "secondary_reporting", "news_article"}


def _fallback_passage(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:2000]


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    stripped = value.strip(" .,;")
    if len(stripped) == 4 and stripped.isdigit():
        return datetime(int(stripped), 12, 31, 23, 59, 59, tzinfo=UTC)
    try:
        parsed = date_parser.parse(stripped, fuzzy=True)
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class HistoricalKnowledgeService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def event_snapshots(
        self,
        event_id: UUID,
        *,
        max_points: int = 100,
    ):
        from collections import Counter

        from newsintel.application.intelligence.dto import (
            EventKnowledgeHistoryView,
            EventKnowledgeSnapshotView,
        )

        async with self._session_factory() as session:
            event = await session.get(EventModel, event_id)
            if event is None:
                return None
            articles = list(
                (
                    await session.scalars(
                        select(ArticleModel).where(ArticleModel.event_id == event_id)
                    )
                ).all()
            )
            article_ids = [item.id for item in articles]
            if not article_ids:
                return EventKnowledgeHistoryView(
                    event_id=event_id,
                    title=event.title,
                    snapshot_basis="stored_observation_and_verification_times",
                    interpretation=(
                        "Snapshots reconstruct what the platform had stored and verified by each timestamp; "
                        "they do not retroactively inject later evidence into earlier states."
                    ),
                    snapshots=[],
                    generated_at=datetime.now(UTC),
                )
            versions = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.article_id.in_(article_ids))
                        .order_by(ArticleVersionModel.retrieved_at)
                    )
                ).all()
            )
            claims = list(
                (
                    await session.scalars(
                        select(ArticleClaimModel)
                        .where(ArticleClaimModel.article_id.in_(article_ids))
                        .order_by(ArticleClaimModel.created_at)
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
            commitments = list(
                (
                    await session.scalars(
                        select(EventCommitmentModel)
                        .where(EventCommitmentModel.event_id == event_id)
                        .order_by(EventCommitmentModel.first_observed_at)
                    )
                ).all()
            )
            commitment_ids = [item.id for item in commitments]
            outcomes = (
                list(
                    (
                        await session.scalars(
                            select(CommitmentOutcomeModel)
                            .where(CommitmentOutcomeModel.commitment_id.in_(commitment_ids))
                            .order_by(CommitmentOutcomeModel.observed_at)
                        )
                    ).all()
                )
                if commitment_ids
                else []
            )

        time_points = {event.first_detected_at}
        time_points.update(item.retrieved_at for item in versions)
        time_points.update(item.created_at for item in verifications)
        time_points.update(item.observed_at for item in outcomes)
        ordered_points = sorted(time_points)
        if len(ordered_points) > max_points:
            ordered_points = _sample_time_points(ordered_points, max_points=max_points)

        article_by_id = {item.id: item for item in articles}
        outcome_by_commitment: dict[UUID, list[CommitmentOutcomeModel]] = {}
        for outcome in outcomes:
            outcome_by_commitment.setdefault(outcome.commitment_id, []).append(outcome)

        snapshots = []
        for point in ordered_points:
            visible_versions = [item for item in versions if item.retrieved_at <= point]
            visible_claims = [item for item in claims if item.created_at <= point]
            visible_claim_ids = {item.id for item in visible_claims}
            latest_verification: dict[UUID, ClaimVerificationModel] = {}
            for verification in verifications:
                if verification.created_at <= point and verification.claim_id in visible_claim_ids:
                    latest_verification[verification.claim_id] = verification
            verification_counts = Counter(item.label for item in latest_verification.values())
            confidences = [
                float(item.confidence_score)
                for item in latest_verification.values()
                if item.confidence_score is not None
            ]
            active_publishers = {
                article_by_id[version.article_id].publisher_id for version in visible_versions
            }
            commitment_counts: Counter[str] = Counter()
            for commitment in commitments:
                if commitment.first_observed_at > point:
                    continue
                status_value = OutcomeStatus.PENDING.value
                for outcome in outcome_by_commitment.get(commitment.id, []):
                    if outcome.observed_at <= point and outcome.status not in {
                        OutcomeStatus.UNKNOWN.value,
                        OutcomeStatus.PENDING.value,
                    }:
                        status_value = outcome.status
                commitment_counts[status_value] += 1
            snapshots.append(
                EventKnowledgeSnapshotView(
                    snapshot_at=point,
                    article_version_count=len(visible_versions),
                    publisher_count=len(active_publishers),
                    known_claim_count=len(visible_claims),
                    verification_counts=dict(sorted(verification_counts.items())),
                    average_verification_confidence=(
                        round(sum(confidences) / len(confidences), 4) if confidences else None
                    ),
                    commitment_status_counts=dict(sorted(commitment_counts.items())),
                )
            )
        return EventKnowledgeHistoryView(
            event_id=event_id,
            title=event.title,
            snapshot_basis="stored_observation_and_verification_times",
            interpretation=(
                "Each snapshot is reconstructed only from article versions, claim verifications, "
                "and commitment outcomes already observed by that time. Later evidence remains later."
            ),
            snapshots=snapshots,
            generated_at=datetime.now(UTC),
        )


def _sample_time_points(points: list[datetime], *, max_points: int) -> list[datetime]:
    if len(points) <= max_points:
        return points
    if max_points <= 2:
        return [points[0], points[-1]][:max_points]
    selected = [points[0]]
    span = len(points) - 1
    for index in range(1, max_points - 1):
        selected.append(points[round(index * span / (max_points - 1))])
    selected.append(points[-1])
    deduped: list[datetime] = []
    for point in selected:
        if not deduped or point != deduped[-1]:
            deduped.append(point)
    return deduped
