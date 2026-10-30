from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.entities.registry import (
    search_configured_registry,
    validate_registry_search_template,
)
from newsintel.application.dependencies.service import DerivedArtifactDependencyService
from newsintel.application.intelligence.accuracy_service import VerificationBenchmarkService
from newsintel.application.intelligence.dto import (
    ClaimReviewFlagView,
    CorrectionEventView,
    CorrectionCandidateView,
    CorrectionDetectionView,
    CorrectionDependencyImpactView,
    CorrectionDependencyPropagationView,
    CorrectionRegisterCommand,
    EntityRegistryCandidateView,
    EntityRegistryCreateCommand,
    EntityRegistryLinkCommand,
    EntityRegistryLinkView,
    EntityRegistryView,
    EvidenceSearchStoppingCommand,
    EvidenceSearchStoppingView,
    OwnershipIngestCommand,
    OwnershipIngestView,
    QualityGateCommand,
    QualityGateView,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.correction_detection import (
    CORRECTION_DETECTION_VERSION,
    detect_correction_candidate,
)
from newsintel.domain.intelligence.entity_linking import normalize_external_identifier
from newsintel.domain.intelligence.entity_registry import (
    EntityDescriptor,
    resolve_registry_candidates,
)
from newsintel.domain.intelligence.propagation import plan_correction_propagation
from newsintel.domain.intelligence.dependency_propagation import (
    DEPENDENCY_PROPAGATION_VERSION,
    classify_dependency_impact,
)
from newsintel.domain.intelligence.release_gates import (
    QualityGateInput,
    assess_verification_quality_gate,
)
from newsintel.domain.intelligence.versioning import diff_article_versions
from newsintel.domain.intelligence.search_stopping import (
    SearchRoundObservation,
    assess_evidence_search_stopping,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleCorrectionEventModel,
    ArticleModel,
    ArticleVersionModel,
    CanonicalEntityModel,
    ClaimConflictResolutionModel,
    ClaimReviewFlagModel,
    ClaimEvidenceLinkModel,
    CorrectionDependencyPropagationRunModel,
    EntityAliasModel,
    EntityExternalIdentifierModel,
    EntityRegistryLinkRunModel,
    EntityRegistryProfileModel,
    EvidenceOrchestrationRunModel,
    EvidencePassageEvaluationModel,
    EvidenceSearchRunModel,
    EvidenceSearchStoppingAssessmentModel,
    MediaOwnershipGroupModel,
    OwnershipIngestRunModel,
    OwnershipProvenanceRecordModel,
    PublisherModel,
    PublisherOwnershipMembershipModel,
    TemporalKnowledgeEdgeModel,
    TemporalKnowledgeNodeModel,
    VerificationQualityGateRunModel,
)


class EvidenceSearchStoppingService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def assess(
        self,
        claim_id: UUID,
        run_id: UUID,
        command: EvidenceSearchStoppingCommand,
    ) -> EvidenceSearchStoppingView | None:
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            run = await session.get(EvidenceSearchRunModel, run_id)
            if claim is None or run is None or run.claim_id != claim_id:
                return None
            orchestrations = list(
                (
                    await session.scalars(
                        select(EvidenceOrchestrationRunModel)
                        .where(EvidenceOrchestrationRunModel.claim_id == claim_id)
                        .order_by(EvidenceOrchestrationRunModel.created_at)
                    )
                ).all()
            )
            evidence = list(
                (
                    await session.scalars(
                        select(EvidencePassageEvaluationModel)
                        .where(EvidencePassageEvaluationModel.claim_id == claim_id)
                        .order_by(EvidencePassageEvaluationModel.retrieved_at)
                    )
                ).all()
            )
            latest_conflict = await session.scalar(
                select(ClaimConflictResolutionModel)
                .where(ClaimConflictResolutionModel.claim_id == claim_id)
                .order_by(ClaimConflictResolutionModel.created_at.desc())
                .limit(1)
            )

        required = _required_classes(run)
        covered_classes = tuple(
            dict.fromkeys(
                item.evidence_class
                for item in evidence
                if item.evidence_class and item.stance not in {"irrelevant", "insufficient"}
            )
        )
        rounds: list[SearchRoundObservation] = []
        for index, orchestration in enumerate(orchestrations, start=1):
            execution = orchestration.metadata_.get("execution") if isinstance(orchestration.metadata_, dict) else None
            execution = execution if isinstance(execution, dict) else {}
            documents = _int(execution.get("documents_retrieved"))
            evaluations = _int(execution.get("evaluations_created"))
            authorities = _int(execution.get("authorities_attempted"))
            rounds.append(
                SearchRoundObservation(
                    round_number=index,
                    authorities_attempted=authorities,
                    documents_retrieved=documents,
                    new_lineages=min(documents, evaluations),
                    new_primary_records=0,
                    covered_evidence_classes=covered_classes,
                    authority_exhausted=authorities > 0 and documents == 0,
                )
            )
        if not rounds:
            rounds.append(
                SearchRoundObservation(
                    round_number=1,
                    authorities_attempted=0,
                    documents_retrieved=0,
                    new_lineages=0,
                    new_primary_records=0,
                    covered_evidence_classes=covered_classes,
                )
            )

        lineages = _independent_lineages(evidence)
        primary_records = len({item.source_url for item in evidence if item.primary_source})
        result = assess_evidence_search_stopping(
            tuple(required),
            tuple(rounds),
            independent_lineages=lineages,
            primary_records=primary_records,
            conflict_state=latest_conflict.state if latest_conflict else None,
            max_rounds=command.max_rounds,
            min_independent_lineages=command.min_independent_lineages,
            require_primary_record=command.require_primary_record,
        )
        now = datetime.now(UTC)
        model = EvidenceSearchStoppingAssessmentModel(
            id=uuid7(),
            claim_id=claim_id,
            search_run_id=run_id,
            methodology_version=result.methodology_version,
            decision=result.decision.value,
            completeness_score=result.completeness_score,
            covered_evidence_classes=list(result.covered_evidence_classes),
            uncovered_evidence_classes=list(result.uncovered_evidence_classes),
            independent_lineages=result.independent_lineages,
            primary_records=result.primary_records,
            rounds_completed=result.rounds_completed,
            metadata_={**result.metadata, "rationale": result.rationale},
            created_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(model)
            await session.flush()
        return _stopping_view(model)

    async def history(self, claim_id: UUID, *, limit: int = 50) -> list[EvidenceSearchStoppingView] | None:
        async with self._session_factory() as session:
            if await session.get(ArticleClaimModel, claim_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(EvidenceSearchStoppingAssessmentModel)
                        .where(EvidenceSearchStoppingAssessmentModel.claim_id == claim_id)
                        .order_by(EvidenceSearchStoppingAssessmentModel.created_at.desc())
                        .limit(min(200, max(1, limit)))
                    )
                ).all()
            )
        return [_stopping_view(item) for item in rows]


class CorrectionPropagationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._dependencies = DerivedArtifactDependencyService(session_factory)

    async def register(
        self,
        article_id: UUID,
        command: CorrectionRegisterCommand,
    ) -> CorrectionEventView | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            article = await session.get(ArticleModel, article_id)
            if article is None:
                return None
            version = None
            if command.article_version_id is not None:
                version = await session.get(ArticleVersionModel, command.article_version_id)
                if version is None or version.article_id != article_id:
                    raise ValueError("article_version_id does not belong to the article")

            statement = select(ArticleClaimModel).where(ArticleClaimModel.article_id == article_id)
            if command.affected_claim_ids:
                statement = statement.where(ArticleClaimModel.id.in_(command.affected_claim_ids))
            elif version is not None:
                statement = statement.where(ArticleClaimModel.article_version_id == version.id)
            claims = list((await session.scalars(statement.order_by(ArticleClaimModel.created_at))).all())
            if command.affected_claim_ids and len({item.id for item in claims}) != len(set(command.affected_claim_ids)):
                raise ValueError("one or more affected claims do not belong to the article")

            plan = plan_correction_propagation(
                command.correction_kind,
                tuple(str(item.id) for item in claims),
            )
            serialized_plan = {
                "methodology_version": plan.methodology_version,
                "correction_kind": plan.correction_kind.value,
                "automatic_verdict_change": plan.automatic_verdict_change,
                "event_actions": [item.value for item in plan.event_actions],
                "publisher_actions": [item.value for item in plan.publisher_actions],
                "impacts": [
                    {
                        "claim_id": item.claim_id,
                        "actions": [action.value for action in item.actions],
                        "severity": item.severity,
                        "rationale": item.rationale,
                    }
                    for item in plan.impacts
                ],
                "interpretation": plan.interpretation,
            }
            event_model = ArticleCorrectionEventModel(
                id=uuid7(),
                article_id=article_id,
                article_version_id=version.id if version else None,
                event_id=article.event_id,
                correction_kind=plan.correction_kind.value,
                source_url=str(command.source_url) if command.source_url else None,
                note=command.note,
                affected_claim_ids=[str(item.id) for item in claims],
                propagation_plan=serialized_plan,
                created_at=now,
            )
            session.add(event_model)
            await session.flush()

            flags: list[ClaimReviewFlagModel] = []
            impact_by_id = {item.claim_id: item for item in plan.impacts}
            for claim in claims:
                impact = impact_by_id.get(str(claim.id))
                if impact is None or all(action.value == "record_only" for action in impact.actions):
                    continue
                flag = ClaimReviewFlagModel(
                    id=uuid7(),
                    correction_event_id=event_model.id,
                    claim_id=claim.id,
                    state="review_required",
                    severity=impact.severity,
                    actions=[action.value for action in impact.actions],
                    reason=impact.rationale,
                    resolved_at=None,
                    metadata_={
                        "guardrail": "The flag marks prior analysis stale; it does not change the stored verification label.",
                    },
                    created_at=now,
                    updated_at=now,
                )
                session.add(flag)
                flags.append(flag)

            dependency_run = None
            if command.propagate_dependencies:
                dependency_run, dependency_flags = await self._propagate_dependencies(
                    session,
                    correction_event_id=event_model.id,
                    root_article_id=article_id,
                    correction_kind=plan.correction_kind.value,
                    direct_claim_ids={item.id for item in claims},
                    max_depth=command.max_dependency_depth,
                    max_claims=command.max_dependency_claims,
                    created_at=now,
                )
                flags.extend(dependency_flags)
                serialized_plan["dependency_propagation"] = {
                    "run_id": str(dependency_run.id),
                    "methodology_version": dependency_run.methodology_version,
                    "max_depth": dependency_run.max_depth,
                    "direct_dependency_count": dependency_run.direct_dependency_count,
                    "indirect_dependency_count": dependency_run.indirect_dependency_count,
                    "truncated": dependency_run.truncated,
                }
                event_model.propagation_plan = serialized_plan

            correction_key = f"correction:{event_model.id}"
            node = TemporalKnowledgeNodeModel(
                id=uuid7(),
                event_id=article.event_id,
                node_key=correction_key,
                node_type="correction",
                label=f"{plan.correction_kind.value}: {article.title}",
                search_text=f"{plan.correction_kind.value} {article.title} {command.note or ''}".casefold(),
                observed_at=now,
                valid_from=now,
                valid_to=None,
                graph_version=plan.methodology_version,
                payload={
                    "article_id": str(article_id),
                    "article_version_id": str(version.id) if version else None,
                    "affected_claim_ids": [str(item.id) for item in claims],
                    "source_url": str(command.source_url) if command.source_url else None,
                },
                created_at=now,
                updated_at=now,
            )
            session.add(node)
            for claim in claims:
                edge_material = f"{correction_key}|claim:{claim.id}|correction_impacts"
                session.add(
                    TemporalKnowledgeEdgeModel(
                        id=uuid7(),
                        event_id=article.event_id,
                        edge_key=sha256(edge_material.encode("utf-8")).hexdigest(),
                        source_key=correction_key,
                        target_key=f"claim:{claim.id}",
                        relation="correction_impacts",
                        observed_at=now,
                        valid_from=now,
                        valid_to=None,
                        graph_version=plan.methodology_version,
                        payload={"correction_event_id": str(event_model.id)},
                        created_at=now,
                        updated_at=now,
                    )
                )
            invalidated = await self._dependencies.invalidate_source(
                source_kind="article_version" if version is not None else "article",
                source_id=version.id if version is not None else article.id,
                reason=f"correction:{plan.correction_kind.value}",
                session=session,
            )
            invalidated += await self._dependencies.invalidate_source(
                source_kind="event",
                source_id=article.event_id,
                reason=f"event_correction:{plan.correction_kind.value}",
                session=session,
            )
            serialized_plan["derived_artifact_invalidations"] = invalidated
            event_model.propagation_plan = serialized_plan
            await session.flush()
            return _correction_view(event_model, flags)

    async def _propagate_dependencies(
        self,
        session: AsyncSession,
        *,
        correction_event_id: UUID,
        root_article_id: UUID,
        correction_kind: str,
        direct_claim_ids: set[UUID],
        max_depth: int,
        max_claims: int,
        created_at: datetime,
    ) -> tuple[CorrectionDependencyPropagationRunModel, list[ClaimReviewFlagModel]]:
        frontier: set[UUID] = {root_article_id}
        seen_articles: set[UUID] = {root_article_id}
        seen_claims: set[UUID] = set(direct_claim_ids)
        impacts: list[dict[str, object]] = []
        flags: list[ClaimReviewFlagModel] = []
        truncated = False

        for depth in range(1, max_depth + 1):
            if not frontier or len(impacts) >= max_claims:
                break
            version_rows = (
                await session.execute(
                    select(
                        ArticleVersionModel.id,
                        ArticleVersionModel.article_id,
                        ArticleVersionModel.source_url,
                        ArticleVersionModel.final_url,
                    ).where(ArticleVersionModel.article_id.in_(frontier))
                )
            ).all()
            version_to_article = {row.id: row.article_id for row in version_rows}
            version_ids = list(version_to_article)
            article_rows = (
                await session.execute(
                    select(ArticleModel.id, ArticleModel.canonical_url).where(ArticleModel.id.in_(frontier))
                )
            ).all()
            url_to_article: dict[str, UUID] = {row.canonical_url: row.id for row in article_rows}
            for row in version_rows:
                url_to_article[row.source_url] = row.article_id
                url_to_article[row.final_url] = row.article_id

            predicates = [ClaimEvidenceLinkModel.evidence_article_id.in_(frontier)]
            if version_ids:
                predicates.append(ClaimEvidenceLinkModel.evidence_article_version_id.in_(version_ids))
            legacy_rows = (
                await session.execute(
                    select(ClaimEvidenceLinkModel, ArticleClaimModel)
                    .join(ArticleClaimModel, ClaimEvidenceLinkModel.claim_id == ArticleClaimModel.id)
                    .where(or_(*predicates))
                    .order_by(ClaimEvidenceLinkModel.retrieved_at, ClaimEvidenceLinkModel.id)
                )
            ).all()
            passage_rows = []
            if url_to_article:
                passage_rows = (
                    await session.execute(
                        select(EvidencePassageEvaluationModel, ArticleClaimModel)
                        .join(
                            ArticleClaimModel,
                            EvidencePassageEvaluationModel.claim_id == ArticleClaimModel.id,
                        )
                        .where(EvidencePassageEvaluationModel.source_url.in_(list(url_to_article)))
                        .order_by(
                            EvidencePassageEvaluationModel.retrieved_at,
                            EvidencePassageEvaluationModel.id,
                        )
                    )
                ).all()

            next_frontier: set[UUID] = set()
            dependency_rows: list[tuple[object, ArticleClaimModel, UUID | None, str, str]] = []
            for link, claim in legacy_rows:
                via_article_id = link.evidence_article_id
                if via_article_id is None and link.evidence_article_version_id is not None:
                    via_article_id = version_to_article.get(link.evidence_article_version_id)
                dependency_rows.append((link, claim, via_article_id, "claim_evidence_link", str(link.id)))
            for passage, claim in passage_rows:
                dependency_rows.append(
                    (
                        passage,
                        claim,
                        url_to_article.get(passage.source_url),
                        "evidence_passage_evaluation",
                        str(passage.id),
                    )
                )

            for _evidence_record, claim, via_article_id, dependency_type, dependency_id in dependency_rows:
                if claim.id in seen_claims or claim.article_id == root_article_id:
                    continue
                if via_article_id is None:
                    continue
                impact = classify_dependency_impact(
                    correction_kind=correction_kind,
                    claim_id=str(claim.id),
                    claim_article_id=str(claim.article_id),
                    via_article_id=str(via_article_id),
                    depth=depth,
                )
                seen_claims.add(claim.id)
                impact_payload = {
                    "claim_id": str(claim.id),
                    "claim_article_id": str(claim.article_id),
                    "via_article_id": str(via_article_id),
                    "depth": depth,
                    "severity": impact.severity.value,
                    "actions": list(impact.actions),
                    "rationale": impact.rationale,
                    "dependency_type": dependency_type,
                    "dependency_id": dependency_id,
                }
                impacts.append(impact_payload)
                flag = ClaimReviewFlagModel(
                    id=uuid7(),
                    correction_event_id=correction_event_id,
                    claim_id=claim.id,
                    state="review_required",
                    severity=impact.severity.value,
                    actions=list(impact.actions),
                    reason=impact.rationale,
                    resolved_at=None,
                    metadata_={
                        "dependency_depth": depth,
                        "via_article_id": str(via_article_id),
                        "dependency_type": dependency_type,
                        "dependency_id": dependency_id,
                        "methodology_version": DEPENDENCY_PROPAGATION_VERSION,
                        "guardrail": (
                            "Dependency propagation marks downstream analysis for review only; "
                            "it never changes a stored verification label automatically."
                        ),
                    },
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(flag)
                flags.append(flag)
                next_frontier.add(claim.article_id)
                if len(impacts) >= max_claims:
                    truncated = True
                    break
            if truncated:
                break
            frontier = next_frontier - seen_articles
            seen_articles.update(frontier)

        run = CorrectionDependencyPropagationRunModel(
            id=uuid7(),
            correction_event_id=correction_event_id,
            root_article_id=root_article_id,
            methodology_version=DEPENDENCY_PROPAGATION_VERSION,
            correction_kind=correction_kind,
            max_depth=max_depth,
            direct_dependency_count=sum(1 for item in impacts if item["depth"] == 1),
            indirect_dependency_count=sum(1 for item in impacts if int(item["depth"]) > 1),
            truncated=truncated,
            impacts=impacts,
            metadata_={
                "max_dependency_claims": max_claims,
                "guardrail": (
                    "Indirect evidence dependencies are conservative review signals, not proof that "
                    "a dependent claim is incorrect."
                ),
            },
            created_at=created_at,
        )
        session.add(run)
        await session.flush()
        return run, flags

    async def dependency_propagation(
        self, correction_event_id: UUID
    ) -> CorrectionDependencyPropagationView | None:
        async with self._session_factory() as session:
            model = await session.scalar(
                select(CorrectionDependencyPropagationRunModel)
                .where(CorrectionDependencyPropagationRunModel.correction_event_id == correction_event_id)
                .order_by(CorrectionDependencyPropagationRunModel.created_at.desc())
                .limit(1)
            )
        return _dependency_propagation_view(model) if model else None

    async def detect(self, article_id: UUID) -> CorrectionDetectionView | None:
        async with self._session_factory() as session:
            if await session.get(ArticleModel, article_id) is None:
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
        candidates: list[CorrectionCandidateView] = []
        for old, new in zip(versions, versions[1:], strict=False):
            diff = diff_article_versions(
                old_title=old.title,
                old_text=old.text_content,
                new_title=new.title,
                new_text=new.text_content,
            )
            candidate = detect_correction_candidate(
                new_title=new.title,
                new_text=new.text_content,
                version_diff=diff,
            )
            if candidate is None:
                continue
            candidates.append(
                CorrectionCandidateView(
                    from_version_id=old.id,
                    to_version_id=new.id,
                    from_version_number=old.version_number,
                    to_version_number=new.version_number,
                    suggested_kind=candidate.suggested_kind,
                    confidence=candidate.confidence,
                    reason=candidate.reason,
                    material_change_count=diff.material_change_count,
                    numeric_change_count=diff.numeric_change_count,
                    temporal_change_count=diff.temporal_change_count,
                    requires_human_confirmation=candidate.requires_human_confirmation,
                )
            )
        return CorrectionDetectionView(
            article_id=article_id,
            methodology_version=CORRECTION_DETECTION_VERSION,
            candidates=candidates,
            generated_at=datetime.now(UTC),
            interpretation=(
                "Detection surfaces revision candidates only. Human confirmation is required before "
                "a correction/retraction event is registered and propagated."
            ),
        )

    async def history(self, article_id: UUID) -> list[CorrectionEventView] | None:
        async with self._session_factory() as session:
            if await session.get(ArticleModel, article_id) is None:
                return None
            events = list(
                (
                    await session.scalars(
                        select(ArticleCorrectionEventModel)
                        .where(ArticleCorrectionEventModel.article_id == article_id)
                        .order_by(ArticleCorrectionEventModel.created_at.desc())
                    )
                ).all()
            )
            result: list[CorrectionEventView] = []
            for event in events:
                flags = list(
                    (
                        await session.scalars(
                            select(ClaimReviewFlagModel)
                            .where(ClaimReviewFlagModel.correction_event_id == event.id)
                            .order_by(ClaimReviewFlagModel.created_at)
                        )
                    ).all()
                )
                result.append(_correction_view(event, flags))
            return result

    async def resolve_flag(self, flag_id: UUID, *, note: str | None = None) -> ClaimReviewFlagView | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            flag = await session.get(ClaimReviewFlagModel, flag_id)
            if flag is None:
                return None
            flag.state = "reviewed"
            flag.resolved_at = now
            flag.updated_at = now
            metadata = dict(flag.metadata_)
            if note:
                metadata["resolution_note"] = note
            metadata["resolved_without_automatic_verdict_change"] = True
            flag.metadata_ = metadata
            await session.flush()
            return _review_flag_view(flag)


class VerificationQualityGateService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._benchmark = VerificationBenchmarkService(session_factory)

    async def assess(self, benchmark_set: str, command: QualityGateCommand) -> QualityGateView:
        evaluation = await self._benchmark.assess(benchmark_set, split="test")
        audit = await self._benchmark.audit(benchmark_set)
        selective = next(
            (item for item in evaluation.selective_metrics if abs(item.threshold - 0.8) < 1e-9),
            None,
        )
        input_metrics = QualityGateInput(
            case_count=audit.case_count,
            leakage_case_count=audit.leakage_case_count,
            group_leakage_count=len(audit.group_leakage_keys),
            source_document_leakage_count=len(audit.source_document_leakage_keys),
            macro_f1=evaluation.macro_f1,
            high_confidence_error_rate=evaluation.high_confidence_error_rate,
            test_split_count=audit.split_counts.get("test", 0),
            selective_accuracy_80=selective.accuracy if selective else None,
            selective_coverage_80=selective.coverage if selective else None,
            decision_coverage=evaluation.decision_coverage,
            decided_accuracy=evaluation.decided_accuracy,
            unsafe_high_confidence_error_rate=evaluation.unsafe_high_confidence_error_rate,
        )
        result = assess_verification_quality_gate(
            input_metrics,
            min_cases=command.min_cases,
            min_test_cases=command.min_test_cases,
            min_macro_f1=command.min_macro_f1,
            max_high_confidence_error_rate=command.max_high_confidence_error_rate,
            min_selective_accuracy_80=command.min_selective_accuracy_80,
            min_selective_coverage_80=command.min_selective_coverage_80,
            min_decision_coverage=command.min_decision_coverage,
            min_decided_accuracy=command.min_decided_accuracy,
            max_unsafe_high_confidence_error_rate=command.max_unsafe_high_confidence_error_rate,
        )
        thresholds = command.model_dump()
        metrics = {
            "case_count": input_metrics.case_count,
            "test_split_count": input_metrics.test_split_count,
            "leakage_case_count": input_metrics.leakage_case_count,
            "group_leakage_count": input_metrics.group_leakage_count,
            "source_document_leakage_count": input_metrics.source_document_leakage_count,
            "macro_f1": input_metrics.macro_f1,
            "high_confidence_error_rate": input_metrics.high_confidence_error_rate,
            "selective_accuracy_80": input_metrics.selective_accuracy_80,
            "selective_coverage_80": input_metrics.selective_coverage_80,
            "decision_coverage": input_metrics.decision_coverage,
            "decided_accuracy": input_metrics.decided_accuracy,
            "unsafe_high_confidence_error_rate": input_metrics.unsafe_high_confidence_error_rate,
            "corpus_readiness": audit.readiness,
        }
        now = datetime.now(UTC)
        model = VerificationQualityGateRunModel(
            id=uuid7(),
            benchmark_set=benchmark_set,
            evaluation_id=evaluation.id,
            methodology_version=result.methodology_version,
            state=result.state.value,
            failures=list(result.failures),
            warnings=list(result.warnings),
            thresholds=thresholds,
            metrics=metrics,
            metadata_={
                "interpretation": result.interpretation,
                "benchmark_audit_warnings": audit.warnings,
                "guardrail": "A passing quality gate applies only to the adjudicated held-out benchmark scope.",
            },
            created_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(model)
            await session.flush()
        return _quality_gate_view(model)

    async def history(self, benchmark_set: str, *, limit: int = 50) -> list[QualityGateView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(VerificationQualityGateRunModel)
                        .where(VerificationQualityGateRunModel.benchmark_set == benchmark_set)
                        .order_by(VerificationQualityGateRunModel.created_at.desc())
                        .limit(min(200, max(1, limit)))
                    )
                ).all()
            )
        return [_quality_gate_view(item) for item in rows]


class EntityRegistryService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], fetcher) -> None:
        self._session_factory = session_factory
        self._fetcher = fetcher

    async def create_profile(self, command: EntityRegistryCreateCommand) -> EntityRegistryView:
        validate_registry_search_template(str(command.base_url), command.search_url_template)
        if command.adapter_type != "configured_json":
            raise ValueError("only configured_json entity registry adapter is supported in v0.9")
        if "id_field" not in command.config or "label_field" not in command.config:
            raise ValueError("registry config requires id_field and label_field")
        now = datetime.now(UTC)
        model = EntityRegistryProfileModel(
            id=uuid7(),
            name=command.name,
            namespace=command.namespace.casefold(),
            base_url=str(command.base_url),
            search_url_template=command.search_url_template,
            entity_type=command.entity_type,
            jurisdiction=command.jurisdiction,
            language=command.language,
            adapter_type=command.adapter_type,
            config=command.config,
            active=command.active,
            created_at=now,
            updated_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(model)
            await session.flush()
        return _registry_view(model)

    async def list_profiles(self) -> list[EntityRegistryView]:
        async with self._session_factory() as session:
            rows = list((await session.scalars(select(EntityRegistryProfileModel).order_by(EntityRegistryProfileModel.name))).all())
        return [_registry_view(item) for item in rows]

    async def link(self, entity_id: UUID, command: EntityRegistryLinkCommand) -> EntityRegistryLinkView | None:
        async with self._session_factory() as session:
            entity = await session.get(CanonicalEntityModel, entity_id)
            profile = await session.get(EntityRegistryProfileModel, command.registry_profile_id)
            if entity is None or profile is None or not profile.active:
                return None
            aliases = list(
                (
                    await session.scalars(
                        select(EntityAliasModel).where(EntityAliasModel.entity_id == entity_id)
                    )
                ).all()
            )
        search_result = await search_configured_registry(
            self._fetcher,
            base_url=profile.base_url,
            search_url_template=profile.search_url_template,
            query=entity.canonical_name,
            config=profile.config,
            max_results=command.max_results,
        )
        resolution = resolve_registry_candidates(
            EntityDescriptor(
                name=entity.canonical_name,
                entity_type=entity.entity_type,
                aliases=tuple(item.alias for item in aliases),
                country=entity.country_code,
            ),
            search_result.candidates,
            threshold=command.threshold,
            ambiguity_margin=command.ambiguity_margin,
        )
        now = datetime.now(UTC)
        selected = resolution.selected
        candidate_payload = [
            {
                "external_id": item.external_id,
                "label": item.label,
                "score": item.score,
                "canonical_url": _safe_registry_url(item.canonical_url, profile.base_url),
                "reasons": list(item.reasons),
            }
            for item in resolution.candidates
        ]
        run = EntityRegistryLinkRunModel(
            id=uuid7(),
            entity_id=entity_id,
            registry_profile_id=profile.id,
            methodology_version=resolution.methodology_version,
            state=resolution.state.value,
            selected_external_id=selected.external_id if selected else None,
            selected_score=selected.score if selected else None,
            candidates=candidate_payload,
            search_url=search_result.search_url,
            response_sha256=search_result.response_sha256,
            metadata_={
                "interpretation": resolution.interpretation,
                "persist_match_requested": command.persist_match,
                "guardrail": "External registry identity does not validate claims about the entity.",
            },
            created_at=now,
        )
        linked_id: UUID | None = None
        async with self._session_factory() as session, session.begin():
            session.add(run)
            if selected is not None and command.persist_match:
                try:
                    namespace, external_id = normalize_external_identifier(profile.namespace, selected.external_id)
                except ValueError as exc:
                    metadata = dict(run.metadata_)
                    metadata["link_persist_error"] = str(exc)
                    run.metadata_ = metadata
                else:
                    existing = await session.scalar(
                        select(EntityExternalIdentifierModel).where(
                            EntityExternalIdentifierModel.namespace == namespace,
                            EntityExternalIdentifierModel.external_id == external_id,
                        )
                    )
                    if existing is not None:
                        if existing.entity_id == entity_id:
                            linked_id = existing.id
                        else:
                            metadata = dict(run.metadata_)
                            metadata["link_persist_error"] = "external identifier is already linked to another canonical entity"
                            run.metadata_ = metadata
                    else:
                        link = EntityExternalIdentifierModel(
                            id=uuid7(),
                            entity_id=entity_id,
                            namespace=namespace,
                            external_id=external_id,
                            canonical_url=_safe_registry_url(selected.canonical_url, profile.base_url),
                            provenance_url=search_result.search_url,
                            confidence=selected.score,
                            verified_at=now,
                            metadata_={"registry_profile_id": str(profile.id), "automated_identity_match": True},
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(link)
                        await session.flush()
                        linked_id = link.id
            await session.flush()
        return _registry_link_view(run, linked_id)


class OwnershipHistoryIngestService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ingest(self, command: OwnershipIngestCommand) -> OwnershipIngestView:
        now = datetime.now(UTC)
        observed_at = _utc(command.observed_at) or now
        created_memberships = 0
        created_provenance = 0
        rejected: list[dict[str, object]] = []
        async with self._session_factory() as session, session.begin():
            for index, item in enumerate(command.items):
                if item.valid_from and item.valid_to and item.valid_to < item.valid_from:
                    rejected.append({"index": index, "reason": "valid_to earlier than valid_from"})
                    continue
                publisher = await session.get(PublisherModel, item.publisher_id)
                group = await session.get(MediaOwnershipGroupModel, item.group_id)
                if publisher is None or group is None:
                    rejected.append({"index": index, "reason": "publisher or ownership group not found"})
                    continue
                statement = select(PublisherOwnershipMembershipModel).where(
                    PublisherOwnershipMembershipModel.publisher_id == item.publisher_id,
                    PublisherOwnershipMembershipModel.group_id == item.group_id,
                    PublisherOwnershipMembershipModel.relationship == item.relationship.value,
                )
                memberships = list((await session.scalars(statement)).all())
                membership = next(
                    (
                        current
                        for current in memberships
                        if _same_time(current.valid_from, item.valid_from)
                        and _same_time(current.valid_to, item.valid_to)
                    ),
                    None,
                )
                if membership is None:
                    membership = PublisherOwnershipMembershipModel(
                        id=uuid7(),
                        publisher_id=item.publisher_id,
                        group_id=item.group_id,
                        relationship=item.relationship.value,
                        ownership_fraction=item.ownership_fraction,
                        valid_from=_utc(item.valid_from),
                        valid_to=_utc(item.valid_to),
                        provenance_url=str(item.source_url),
                        confidence=item.confidence,
                        metadata_={"ingested_source": command.source_name},
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(membership)
                    await session.flush()
                    created_memberships += 1
                passage = item.passage_text.strip() if item.passage_text else None
                passage_hash = sha256(passage.encode("utf-8")).hexdigest() if passage else None
                existing_provenance = await session.scalar(
                    select(OwnershipProvenanceRecordModel).where(
                        OwnershipProvenanceRecordModel.membership_id == membership.id,
                        OwnershipProvenanceRecordModel.source_url == str(item.source_url),
                        OwnershipProvenanceRecordModel.passage_sha256 == passage_hash,
                    ).limit(1)
                )
                if existing_provenance is None:
                    session.add(
                        OwnershipProvenanceRecordModel(
                            id=uuid7(),
                            membership_id=membership.id,
                            source_url=str(item.source_url),
                            source_type=item.source_type,
                            passage_text=passage,
                            passage_sha256=passage_hash,
                            observed_at=observed_at,
                            valid_from=_utc(item.valid_from),
                            valid_to=_utc(item.valid_to),
                            confidence=item.confidence,
                            metadata_={
                                "ingested_source": command.source_name,
                                "guardrail": "Ownership provenance affects independence analysis only.",
                            },
                            created_at=now,
                        )
                    )
                    created_provenance += 1
            run = OwnershipIngestRunModel(
                id=uuid7(),
                source_name=command.source_name,
                source_url=str(command.source_url) if command.source_url else None,
                observed_at=observed_at,
                input_count=len(command.items),
                membership_created_count=created_memberships,
                provenance_created_count=created_provenance,
                rejected_count=len(rejected),
                metadata_={
                    "rejected_items": rejected,
                    "guardrail": "Bulk ownership ingestion records provenance; it does not infer editorial bias or factuality.",
                },
                created_at=now,
            )
            session.add(run)
            await session.flush()
        return OwnershipIngestView(
            id=run.id,
            source_name=run.source_name,
            source_url=run.source_url,
            observed_at=run.observed_at,
            input_count=run.input_count,
            membership_created_count=run.membership_created_count,
            provenance_created_count=run.provenance_created_count,
            rejected_count=run.rejected_count,
            rejected_items=rejected,
            created_at=run.created_at,
            interpretation=(
                "Ownership history was ingested as time-bounded provenance for independence analysis. "
                "No editorial or factuality conclusion is derived from ownership alone."
            ),
        )


def _required_classes(run: EvidenceSearchRunModel) -> list[str]:
    requirements = run.plan.get("requirements") if isinstance(run.plan, dict) else None
    values: list[str] = []
    if isinstance(requirements, list):
        for item in requirements:
            if isinstance(item, dict) and isinstance(item.get("evidence_class"), str):
                value = str(item["evidence_class"])
                if value not in values:
                    values.append(value)
    return values


def _independent_lineages(evidence: list[EvidencePassageEvaluationModel]) -> int:
    keys: set[str] = set()
    for item in evidence:
        if item.independence_score <= 0.05:
            continue
        metadata = item.metadata_ if isinstance(item.metadata_, dict) else {}
        lineage = metadata.get("lineage_key")
        if isinstance(lineage, str) and lineage.strip():
            keys.add(lineage.strip())
            continue
        host = urlsplit(item.source_url).hostname or item.source_url
        keys.add(host.casefold())
    return len(keys)


def _stopping_view(model: EvidenceSearchStoppingAssessmentModel) -> EvidenceSearchStoppingView:
    return EvidenceSearchStoppingView(
        id=model.id,
        claim_id=model.claim_id,
        run_id=model.search_run_id,
        methodology_version=model.methodology_version,
        decision=model.decision,
        completeness_score=model.completeness_score,
        covered_evidence_classes=list(model.covered_evidence_classes),
        uncovered_evidence_classes=list(model.uncovered_evidence_classes),
        independent_lineages=model.independent_lineages,
        primary_records=model.primary_records,
        rounds_completed=model.rounds_completed,
        rationale=str(model.metadata_.get("rationale") or ""),
        metadata=model.metadata_,
        created_at=model.created_at,
    )


def _review_flag_view(model: ClaimReviewFlagModel) -> ClaimReviewFlagView:
    return ClaimReviewFlagView(
        id=model.id,
        correction_event_id=model.correction_event_id,
        claim_id=model.claim_id,
        state=model.state,
        severity=model.severity,
        actions=list(model.actions),
        reason=model.reason,
        resolved_at=model.resolved_at,
        metadata=model.metadata_,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _correction_view(model: ArticleCorrectionEventModel, flags: list[ClaimReviewFlagModel]) -> CorrectionEventView:
    return CorrectionEventView(
        id=model.id,
        article_id=model.article_id,
        article_version_id=model.article_version_id,
        event_id=model.event_id,
        correction_kind=model.correction_kind,
        source_url=model.source_url,
        note=model.note,
        affected_claim_ids=[UUID(value) for value in model.affected_claim_ids],
        propagation_plan=model.propagation_plan,
        review_flags=[_review_flag_view(item) for item in flags],
        created_at=model.created_at,
        interpretation=(
            "Correction propagation preserves historical verdicts while marking dependent analysis for review. "
            "Any changed verification outcome must be stored as a new revision."
        ),
    )


def _dependency_propagation_view(
    model: CorrectionDependencyPropagationRunModel,
) -> CorrectionDependencyPropagationView:
    return CorrectionDependencyPropagationView(
        id=model.id,
        correction_event_id=model.correction_event_id,
        root_article_id=model.root_article_id,
        methodology_version=model.methodology_version,
        correction_kind=model.correction_kind,
        max_depth=model.max_depth,
        direct_dependency_count=model.direct_dependency_count,
        indirect_dependency_count=model.indirect_dependency_count,
        truncated=model.truncated,
        impacts=[
            CorrectionDependencyImpactView(
                claim_id=UUID(str(item["claim_id"])),
                claim_article_id=UUID(str(item["claim_article_id"])),
                via_article_id=UUID(str(item["via_article_id"])),
                depth=int(item["depth"]),
                severity=str(item["severity"]),
                actions=[str(value) for value in item.get("actions", [])],
                rationale=str(item.get("rationale") or ""),
            )
            for item in model.impacts
        ],
        metadata=model.metadata_,
        created_at=model.created_at,
    )


def _quality_gate_view(model: VerificationQualityGateRunModel) -> QualityGateView:
    return QualityGateView(
        id=model.id,
        benchmark_set=model.benchmark_set,
        evaluation_id=model.evaluation_id,
        methodology_version=model.methodology_version,
        state=model.state,
        failures=list(model.failures),
        warnings=list(model.warnings),
        thresholds=model.thresholds,
        metrics=model.metrics,
        metadata=model.metadata_,
        created_at=model.created_at,
        interpretation=str(model.metadata_.get("interpretation") or ""),
    )


def _registry_view(model: EntityRegistryProfileModel) -> EntityRegistryView:
    return EntityRegistryView(
        id=model.id,
        name=model.name,
        namespace=model.namespace,
        base_url=model.base_url,
        search_url_template=model.search_url_template,
        entity_type=model.entity_type,
        jurisdiction=model.jurisdiction,
        language=model.language,
        adapter_type=model.adapter_type,
        config=model.config,
        active=model.active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _registry_link_view(model: EntityRegistryLinkRunModel, linked_id: UUID | None) -> EntityRegistryLinkView:
    return EntityRegistryLinkView(
        id=model.id,
        entity_id=model.entity_id,
        registry_profile_id=model.registry_profile_id,
        methodology_version=model.methodology_version,
        state=model.state,
        selected_external_id=model.selected_external_id,
        selected_score=model.selected_score,
        candidates=[EntityRegistryCandidateView(**item) for item in model.candidates],
        search_url=model.search_url,
        response_sha256=model.response_sha256,
        linked_identifier_id=linked_id,
        metadata=model.metadata_,
        created_at=model.created_at,
        interpretation=str(model.metadata_.get("interpretation") or ""),
    )


def _safe_registry_url(candidate_url: str | None, base_url: str) -> str | None:
    if not candidate_url:
        return None
    candidate = urlsplit(candidate_url)
    base = urlsplit(base_url)
    if candidate.scheme not in {"http", "https"} or not candidate.hostname or not base.hostname:
        return None
    if candidate.hostname.casefold().strip(".") != base.hostname.casefold().strip("."):
        return None
    return candidate_url


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _same_time(left: datetime | None, right: datetime | None) -> bool:
    return _utc(left) == _utc(right)


def _int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
