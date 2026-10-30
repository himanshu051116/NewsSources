from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.intelligence.advanced_service import EvidenceRetrievalService
from newsintel.application.intelligence.dto import (
    BenchmarkLabelMetricsView,
    BenchmarkSelectiveMetricsView,
    BenchmarkCorpusAuditView,
    ConflictResolutionView,
    EntityExternalIdentifierLinkCommand,
    EntityExternalIdentifierView,
    EvidenceAuthoritySelectionView,
    EvidenceOrchestrationCommand,
    EvidenceOrchestrationView,
    EvidenceSearchExecuteCommand,
    TemporalKnowledgeEdgeView,
    TemporalKnowledgeNeighborhoodView,
    TemporalKnowledgeNodeView,
    VerificationBenchmarkEvaluationView,
    AdjudicationAgreementView,
    AccuracyDiagnosticView,
    ValidationProgramView,
    ValidationConfidenceIntervalView,
    ValidationSliceView,
    ActiveSamplingTargetView,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.benchmarking import (
    BenchmarkObservation,
    assess_verification_benchmark,
)
from newsintel.domain.intelligence.adjudication import AdjudicationReview, assess_adjudication_agreement
from newsintel.domain.intelligence.accuracy_diagnostics import DiagnosticCase, assess_accuracy_failures
from newsintel.domain.intelligence.validation_program import ValidationObservation, build_validation_program_report
from newsintel.domain.intelligence.benchmark_corpus import (
    BenchmarkCorpusCase,
    audit_benchmark_corpus,
)
from newsintel.domain.intelligence.conflict_resolution import (
    ConflictEvidence,
    resolve_evidence_conflict,
)
from newsintel.domain.intelligence.entity_linking import normalize_external_identifier
from newsintel.domain.intelligence.orchestration import (
    AuthorityOption,
    plan_authority_orchestration,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    CanonicalEntityModel,
    ClaimConflictResolutionModel,
    EntityExternalIdentifierModel,
    EvidenceAuthorityProfileModel,
    EvidenceOrchestrationRunModel,
    EvidencePassageEvaluationModel,
    EvidenceRetrievalAttemptModel,
    EvidenceSearchRunModel,
    EventModel,
    TemporalKnowledgeEdgeModel,
    TemporalKnowledgeNodeModel,
    VerificationBenchmarkCaseModel,
    VerificationBenchmarkEvaluationModel,
    VerificationBenchmarkAdjudicationModel,
    VerificationBenchmarkDiagnosticRunModel,
    ArticleVersionModel,
    ArticleModel,
)


class EvidenceOrchestrationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], fetcher) -> None:
        self._session_factory = session_factory
        self._retrieval = EvidenceRetrievalService(session_factory, fetcher)

    async def execute(
        self,
        claim_id: UUID,
        run_id: UUID,
        command: EvidenceOrchestrationCommand,
    ) -> EvidenceOrchestrationView | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            run = await session.get(EvidenceSearchRunModel, run_id)
            if claim is None or run is None or run.claim_id != claim_id:
                return None
            requirements = _required_classes(run)
            statement = select(EvidenceAuthorityProfileModel).where(EvidenceAuthorityProfileModel.active.is_(True))
            if requirements:
                statement = statement.where(EvidenceAuthorityProfileModel.evidence_class.in_(requirements))
            authorities = list((await session.scalars(statement.order_by(EvidenceAuthorityProfileModel.name))).all())
            authority_ids = [item.id for item in authorities]
            attempts = []
            if authority_ids:
                attempts = list(
                    (
                        await session.scalars(
                            select(EvidenceRetrievalAttemptModel).where(
                                EvidenceRetrievalAttemptModel.authority_profile_id.in_(authority_ids)
                            )
                        )
                    ).all()
                )
        attempts_by_authority: dict[UUID, list[EvidenceRetrievalAttemptModel]] = defaultdict(list)
        for attempt in attempts:
            attempts_by_authority[attempt.authority_profile_id].append(attempt)
        options: list[AuthorityOption] = []
        for authority in authorities:
            authority_attempts = attempts_by_authority.get(authority.id, [])
            candidate_attempts = [item for item in authority_attempts if item.candidate_url is not None]
            successes = [
                item for item in candidate_attempts
                if item.status == "candidate_fetched" and item.http_status is not None and 200 <= item.http_status < 300
            ]
            success_rate = len(successes) / len(candidate_attempts) if candidate_attempts else None
            options.append(
                AuthorityOption(
                    authority_id=str(authority.id),
                    evidence_class=authority.evidence_class,
                    jurisdiction=authority.jurisdiction,
                    language=authority.language,
                    authority_domain=urlsplit(authority.base_url).hostname,
                    active=authority.active,
                    prior_success_rate=success_rate,
                    prior_attempted=any(item.search_run_id == run_id for item in authority_attempts),
                )
            )
        plan = plan_authority_orchestration(
            tuple(requirements),
            tuple(options),
            jurisdiction=command.jurisdiction,
            language=command.language,
            max_authorities=command.max_authorities,
        )
        model = EvidenceOrchestrationRunModel(
            id=uuid7(),
            search_run_id=run_id,
            claim_id=claim_id,
            orchestration_version=plan.orchestration_version,
            required_evidence_classes=list(requirements),
            selected_authority_ids=[item.authority_id for item in plan.selections],
            uncovered_evidence_classes=list(plan.uncovered_evidence_classes),
            coverage_ratio=plan.coverage_ratio,
            status="planned" if plan.selections else "blocked_no_authority",
            metadata_={
                "jurisdiction": command.jurisdiction,
                "language": command.language,
                "selections": [
                    {
                        "authority_id": item.authority_id,
                        "evidence_class": item.evidence_class,
                        "score": item.score,
                        "reason": item.reason,
                    }
                    for item in plan.selections
                ],
                "interpretation": plan.interpretation,
            },
            created_at=now,
            updated_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(model)
            await session.flush()

        execution = None
        if plan.selections:
            execution = await self._retrieval.execute(
                claim_id,
                run_id,
                EvidenceSearchExecuteCommand(
                    authority_ids=[UUID(item.authority_id) for item in plan.selections],
                    max_authorities=len(plan.selections),
                    max_candidates_per_authority=command.max_candidates_per_authority,
                    query_override=command.query_override,
                ),
            )
            async with self._session_factory() as session, session.begin():
                persisted = await session.get(EvidenceOrchestrationRunModel, model.id)
                if persisted is not None:
                    persisted.status = "executed" if execution is not None else "execution_failed"
                    persisted.updated_at = datetime.now(UTC)
                    metadata = dict(persisted.metadata_)
                    if execution is not None:
                        metadata["execution"] = {
                            "authorities_attempted": execution.authorities_attempted,
                            "documents_retrieved": execution.documents_retrieved,
                            "evaluations_created": execution.evaluations_created,
                        }
                    persisted.metadata_ = metadata
                    model.status = persisted.status
                    model.updated_at = persisted.updated_at
                    model.metadata_ = persisted.metadata_
        return _orchestration_view(model, execution)


class ConflictResolutionService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(self, claim_id: UUID) -> ConflictResolutionView | None:
        async with self._session_factory() as session:
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(EvidencePassageEvaluationModel)
                        .where(EvidencePassageEvaluationModel.claim_id == claim_id)
                        .order_by(EvidencePassageEvaluationModel.retrieved_at)
                    )
                ).all()
            )
        evidence = tuple(
            ConflictEvidence(
                stance=item.stance,
                confidence=item.stance_confidence,
                independence_score=item.independence_score,
                primary_source=item.primary_source,
                temporal_relation=item.temporal_relation,
                lineage_key=_string(item.metadata_.get("lineage_key")),
                source_key=item.source_url,
            )
            for item in rows
        )
        result = resolve_evidence_conflict(evidence)
        now = datetime.now(UTC)
        model = ClaimConflictResolutionModel(
            id=uuid7(),
            claim_id=claim_id,
            resolver_version=result.resolver_version,
            state=result.state.value,
            confidence=result.confidence,
            support_weight=result.support_weight,
            contradiction_weight=result.contradiction_weight,
            dispute_weight=result.dispute_weight,
            temporal_update_weight=result.temporal_update_weight,
            independent_lineage_count=result.independent_lineage_count,
            primary_support=result.primary_support,
            primary_contradiction=result.primary_contradiction,
            metadata_={
                **result.metadata,
                "rationale": result.rationale,
                "evidence_evaluation_count": len(rows),
            },
            created_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(model)
            await session.flush()
        return _conflict_view(model)

    async def history(self, claim_id: UUID, *, limit: int = 50) -> list[ConflictResolutionView] | None:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        async with self._session_factory() as session:
            if await session.get(ArticleClaimModel, claim_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(ClaimConflictResolutionModel)
                        .where(ClaimConflictResolutionModel.claim_id == claim_id)
                        .order_by(ClaimConflictResolutionModel.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )
        return [_conflict_view(item) for item in rows]


class VerificationBenchmarkService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def assess(
        self,
        benchmark_set: str,
        *,
        split: str | None = None,
        topic_key: str | None = None,
        language: str | None = None,
        jurisdiction: str | None = None,
    ) -> VerificationBenchmarkEvaluationView:
        statement = select(VerificationBenchmarkCaseModel).where(
            VerificationBenchmarkCaseModel.benchmark_set == benchmark_set
        )
        if split is not None:
            statement = statement.where(VerificationBenchmarkCaseModel.split == split)
        if topic_key is not None:
            statement = statement.where(VerificationBenchmarkCaseModel.topic_key == topic_key)
        if language is not None:
            statement = statement.where(VerificationBenchmarkCaseModel.language == language)
        if jurisdiction is not None:
            statement = statement.where(VerificationBenchmarkCaseModel.jurisdiction == jurisdiction)
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        statement.order_by(VerificationBenchmarkCaseModel.created_at)
                    )
                ).all()
            )
        result = assess_verification_benchmark(
            tuple(
                BenchmarkObservation(
                    predicted_label=item.predicted_label,
                    predicted_confidence=item.predicted_confidence,
                    adjudicated_label=item.adjudicated_label,
                    weight=item.weight,
                )
                for item in rows
            )
        )
        now = datetime.now(UTC)
        model = VerificationBenchmarkEvaluationModel(
            id=uuid7(),
            benchmark_set=benchmark_set,
            methodology_version=result.methodology_version,
            observation_count=result.observation_count,
            effective_weight=result.effective_weight,
            accuracy=result.accuracy,
            macro_precision=result.macro_precision,
            macro_recall=result.macro_recall,
            macro_f1=result.macro_f1,
            high_confidence_error_rate=result.high_confidence_error_rate,
            per_label=[item.__dict__ if hasattr(item, "__dict__") else {
                "label": item.label, "support": item.support, "precision": item.precision,
                "recall": item.recall, "f1": item.f1,
            } for item in result.per_label],
            confusion_matrix=result.confusion_matrix,
            selective_metrics=[{
                "threshold": item.threshold, "coverage": item.coverage, "accuracy": item.accuracy,
                "error_rate": item.error_rate, "selected_weight": item.selected_weight,
            } for item in result.selective_metrics],
            metadata_={
                "interpretation": result.interpretation,
                "adjudication_case_count": len(rows),
                "decision_metrics": {
                    "decision_weight": result.decision_weight,
                    "decision_coverage": result.decision_coverage,
                    "abstention_rate": result.abstention_rate,
                    "decided_accuracy": result.decided_accuracy,
                    "decided_macro_f1": result.decided_macro_f1,
                    "unsafe_high_confidence_error_rate": result.unsafe_high_confidence_error_rate,
                },
                "scope": {
                    "split": split,
                    "topic_key": topic_key,
                    "language": language,
                    "jurisdiction": jurisdiction,
                },
                "guardrail": "Benchmark accuracy is valid only to the extent the adjudication set is independent and representative. Keep evaluation splits separate from development/tuning data. Decision metrics distinguish substantive verdicts from not-checkable abstentions.",
            },
            created_at=now,
        )
        async with self._session_factory() as session, session.begin():
            session.add(model)
            await session.flush()
        return _benchmark_view(model)

    async def audit(self, benchmark_set: str) -> BenchmarkCorpusAuditView:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(VerificationBenchmarkCaseModel)
                        .where(VerificationBenchmarkCaseModel.benchmark_set == benchmark_set)
                        .order_by(VerificationBenchmarkCaseModel.created_at)
                    )
                ).all()
            )
        result = audit_benchmark_corpus(
            tuple(
                BenchmarkCorpusCase(
                    case_key=item.case_key,
                    claim_key=str(item.claim_id) if item.claim_id else None,
                    split=item.split,
                    adjudicated_label=item.adjudicated_label,
                    group_key=item.group_key,
                    source_document_key=item.source_document_key,
                    topic_key=item.topic_key,
                    language=item.language,
                    jurisdiction=item.jurisdiction,
                    adjudicator_count=item.adjudicator_count,
                    weight=item.weight,
                )
                for item in rows
            )
        )
        return BenchmarkCorpusAuditView(
            benchmark_set=benchmark_set,
            audit_version=result.audit_version,
            case_count=result.case_count,
            effective_weight=result.effective_weight,
            split_counts=result.split_counts,
            label_counts=result.label_counts,
            topic_counts=result.topic_counts,
            language_counts=result.language_counts,
            jurisdiction_counts=result.jurisdiction_counts,
            leakage_keys=list(result.leakage_keys),
            leakage_case_count=result.leakage_case_count,
            duplicate_within_split_keys=list(result.duplicate_within_split_keys),
            group_leakage_keys=list(result.group_leakage_keys),
            source_document_leakage_keys=list(result.source_document_leakage_keys),
            single_adjudicator_ratio=result.single_adjudicator_ratio,
            readiness=result.readiness,
            warnings=list(result.warnings),
            interpretation=result.interpretation,
            generated_at=datetime.now(UTC),
        )

    async def agreement(self, benchmark_set: str) -> AdjudicationAgreementView:
        async with self._session_factory() as session:
            rows = list((await session.scalars(select(VerificationBenchmarkAdjudicationModel).where(VerificationBenchmarkAdjudicationModel.benchmark_set == benchmark_set))).all())
        result = assess_adjudication_agreement(tuple(AdjudicationReview(item.case_key, item.reviewer_key_hash[:12], item.adjudicated_label, item.reviewer_role) for item in rows))
        now = datetime.now(UTC)
        return AdjudicationAgreementView(
            benchmark_set=benchmark_set, methodology_version=result.methodology_version, case_count=result.case_count,
            review_count=result.review_count, multi_review_case_count=result.multi_review_case_count,
            unanimous_case_count=result.unanimous_case_count, disagreement_case_count=result.disagreement_case_count,
            adjudicated_disagreement_count=result.adjudicated_disagreement_count, pairwise_agreement=result.pairwise_agreement,
            krippendorff_alpha_nominal=result.krippendorff_alpha_nominal, label_counts=result.label_counts,
            reviewer_counts=result.reviewer_counts, interpretation=result.interpretation, generated_at=now,
        )

    async def validation_report(
        self,
        benchmark_set: str,
        *,
        split: str | None = "test",
        min_overall_cases: int = 30,
        min_slice_cases: int = 10,
    ) -> ValidationProgramView:
        statement = select(VerificationBenchmarkCaseModel).where(
            VerificationBenchmarkCaseModel.benchmark_set == benchmark_set
        )
        if split is not None:
            statement = statement.where(VerificationBenchmarkCaseModel.split == split)
        async with self._session_factory() as session:
            rows = list((await session.scalars(statement.order_by(VerificationBenchmarkCaseModel.created_at))).all())
        observations = tuple(
            ValidationObservation(
                case_key=item.case_key or str(item.id),
                predicted_label=item.predicted_label,
                adjudicated_label=item.adjudicated_label,
                predicted_confidence=item.predicted_confidence,
                topic_key=item.topic_key,
                language=item.language,
                source_key=item.source_document_key or str((item.metadata_ or {}).get("source_key") or "") or None,
                weight=item.weight,
            )
            for item in rows
        )
        result = build_validation_program_report(
            observations,
            min_overall_cases=min_overall_cases,
            min_slice_cases=min_slice_cases,
        )
        def interval_view(item):
            return ValidationConfidenceIntervalView(
                estimate=item.estimate, lower=item.lower, upper=item.upper, sample_size=item.sample_size
            )
        return ValidationProgramView(
            benchmark_set=benchmark_set,
            methodology_version=result.methodology_version,
            corpus_fingerprint=result.corpus_fingerprint,
            corpus_case_count=result.corpus_case_count,
            decided_case_count=result.decided_case_count,
            decision_coverage=result.decision_coverage,
            decided_accuracy=result.decided_accuracy,
            decided_accuracy_interval=interval_view(result.decided_accuracy_interval),
            unsafe_high_confidence_error_rate=result.unsafe_high_confidence_error_rate,
            overall_gate_state=result.overall_gate_state,
            failures=list(result.failures),
            slice_results=[
                ValidationSliceView(
                    dimension=item.dimension, value=item.value, case_count=item.case_count,
                    decision_count=item.decision_count, decision_coverage=item.decision_coverage,
                    decided_accuracy=item.decided_accuracy, accuracy_interval=interval_view(item.accuracy_interval),
                    unsafe_high_confidence_error_rate=item.unsafe_high_confidence_error_rate,
                    gate_state=item.gate_state, failures=list(item.failures),
                )
                for item in result.slice_results
            ],
            active_sampling_targets=[
                ActiveSamplingTargetView(
                    dimension=item.dimension, value=item.value, priority=item.priority,
                    reason=item.reason, case_count=item.case_count
                )
                for item in result.active_sampling_targets
            ],
            generated_at=datetime.now(UTC),
            interpretation=result.interpretation,
        )

    async def diagnostics(self, benchmark_set: str) -> AccuracyDiagnosticView:
        async with self._session_factory() as session:
            cases = list((await session.scalars(select(VerificationBenchmarkCaseModel).where(VerificationBenchmarkCaseModel.benchmark_set == benchmark_set))).all())
            claim_ids = [item.claim_id for item in cases if item.claim_id is not None]
            claims = list((await session.scalars(select(ArticleClaimModel).where(ArticleClaimModel.id.in_(claim_ids)))).all()) if claim_ids else []
            claim_by_id = {item.id: item for item in claims}
            version_ids = [item.article_version_id for item in claims]
            versions = list((await session.scalars(select(ArticleVersionModel).where(ArticleVersionModel.id.in_(version_ids)))).all()) if version_ids else []
            version_by_id = {item.id: item for item in versions}
            article_ids = list({item.article_id for item in claims})
            articles = list((await session.scalars(select(ArticleModel).where(ArticleModel.id.in_(article_ids)))).all()) if article_ids else []
            article_by_id = {item.id: item for item in articles}
            event_ids = list({item.event_id for item in articles})
            events = list((await session.scalars(select(EventModel).where(EventModel.id.in_(event_ids)))).all()) if event_ids else []
            event_by_id = {item.id: item for item in events}
            evidence = list((await session.scalars(select(EvidencePassageEvaluationModel).where(EvidencePassageEvaluationModel.claim_id.in_(claim_ids)))).all()) if claim_ids else []
            searches = list((await session.scalars(select(EvidenceSearchRunModel).where(EvidenceSearchRunModel.claim_id.in_(claim_ids)))).all()) if claim_ids else []
            conflicts = list((await session.scalars(select(ClaimConflictResolutionModel).where(ClaimConflictResolutionModel.claim_id.in_(claim_ids)).order_by(ClaimConflictResolutionModel.claim_id, ClaimConflictResolutionModel.created_at.desc()))).all()) if claim_ids else []
        evidence_by_claim: dict[UUID, list[EvidencePassageEvaluationModel]] = defaultdict(list)
        for item in evidence: evidence_by_claim[item.claim_id].append(item)
        search_by_claim: dict[UUID, list[EvidenceSearchRunModel]] = defaultdict(list)
        for item in searches: search_by_claim[item.claim_id].append(item)
        latest_conflict: dict[UUID, ClaimConflictResolutionModel] = {}
        for item in conflicts: latest_conflict.setdefault(item.claim_id, item)
        diagnostic_cases = []
        for case in cases:
            claim = claim_by_id.get(case.claim_id) if case.claim_id else None
            version = version_by_id.get(claim.article_version_id) if claim else None
            article = article_by_id.get(claim.article_id) if claim else None
            event = event_by_id.get(article.event_id) if article else None
            evs = evidence_by_claim.get(case.claim_id, []) if case.claim_id else []
            lineages = {str(item.metadata_.get("lineage_key") or item.source_url) for item in evs if item.independence_score > 0}
            searches_for_claim = search_by_claim.get(case.claim_id, []) if case.claim_id else []
            fidelity = None
            if version is not None and isinstance(version.metadata_, dict):
                raw = version.metadata_.get("extraction_fidelity")
                if isinstance(raw, dict): fidelity = str(raw.get("label") or "") or None
            source_url = str((case.metadata_ or {}).get("source_url") or (version.final_url if version else ""))
            source_key = urlsplit(source_url).hostname if source_url else None
            conflict = latest_conflict.get(case.claim_id) if case.claim_id else None
            diagnostic_cases.append(DiagnosticCase(
                case_key=case.case_key or str(case.id), predicted_label=case.predicted_label,
                adjudicated_label=case.adjudicated_label, predicted_confidence=case.predicted_confidence,
                topic_key=case.topic_key, language=case.language, source_key=source_key,
                extraction_fidelity_label=fidelity, event_assignment_state=event.assignment_status if event else None,
                evidence_count=len(evs), independent_lineage_count=len(lineages),
                primary_evidence_count=sum(1 for item in evs if item.primary_source),
                retrieval_complete=any(item.retrieval_complete for item in searches_for_claim),
                unresolved_conflict=(conflict.state == "unresolved_conflict") if conflict else False,
            ))
        result = assess_accuracy_failures(tuple(diagnostic_cases))
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            session.add(VerificationBenchmarkDiagnosticRunModel(
                id=uuid7(), benchmark_set=benchmark_set, methodology_version=result.methodology_version,
                case_count=result.case_count, error_count=result.error_count, error_rate=result.error_rate,
                taxonomy_counts=result.taxonomy_counts,
                slice_metrics={"topic_error_rates": result.topic_error_rates, "language_error_rates": result.language_error_rates, "source_error_rates": result.source_error_rates},
                metadata_={"high_confidence_error_count": result.high_confidence_error_count, "interpretation": result.interpretation},
                created_at=now,
            ))
        return AccuracyDiagnosticView(
            benchmark_set=benchmark_set, methodology_version=result.methodology_version, case_count=result.case_count,
            error_count=result.error_count, error_rate=result.error_rate, taxonomy_counts=result.taxonomy_counts,
            topic_error_rates=result.topic_error_rates, language_error_rates=result.language_error_rates,
            source_error_rates=result.source_error_rates, high_confidence_error_count=result.high_confidence_error_count,
            interpretation=result.interpretation, generated_at=now,
        )

    async def history(self, benchmark_set: str, *, limit: int = 50) -> list[VerificationBenchmarkEvaluationView]:
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(VerificationBenchmarkEvaluationModel)
                        .where(VerificationBenchmarkEvaluationModel.benchmark_set == benchmark_set)
                        .order_by(VerificationBenchmarkEvaluationModel.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )
        return [_benchmark_view(item) for item in rows]


class EntityExternalIdentifierService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def link(
        self,
        entity_id: UUID,
        command: EntityExternalIdentifierLinkCommand,
    ) -> EntityExternalIdentifierView | None:
        namespace, external_id = normalize_external_identifier(command.namespace, command.external_id)
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            entity = await session.get(CanonicalEntityModel, entity_id)
            if entity is None:
                return None
            existing = await session.scalar(
                select(EntityExternalIdentifierModel).where(
                    EntityExternalIdentifierModel.namespace == namespace,
                    EntityExternalIdentifierModel.external_id == external_id,
                )
            )
            if existing is not None and existing.entity_id != entity_id:
                raise ValueError("external identifier is already linked to a different canonical entity")
            if existing is not None:
                return _external_id_view(existing)
            model = EntityExternalIdentifierModel(
                id=uuid7(),
                entity_id=entity_id,
                namespace=namespace,
                external_id=external_id,
                canonical_url=str(command.canonical_url) if command.canonical_url else None,
                provenance_url=str(command.provenance_url) if command.provenance_url else None,
                confidence=command.confidence,
                verified_at=command.verified_at,
                metadata_={
                    **command.metadata,
                    "guardrail": "External identifiers improve entity identity resolution; they do not validate factual claims about the entity.",
                },
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            cache = dict(entity.external_ids or {})
            cache[namespace] = external_id
            entity.external_ids = cache
            entity.updated_at = now
            await session.flush()
            return _external_id_view(model)

    async def list(self, entity_id: UUID) -> list[EntityExternalIdentifierView] | None:
        async with self._session_factory() as session:
            if await session.get(CanonicalEntityModel, entity_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(EntityExternalIdentifierModel)
                        .where(EntityExternalIdentifierModel.entity_id == entity_id)
                        .order_by(EntityExternalIdentifierModel.namespace, EntityExternalIdentifierModel.external_id)
                    )
                ).all()
            )
        return [_external_id_view(item) for item in rows]


class TemporalKnowledgeResearchService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def neighborhood(
        self,
        event_id: UUID,
        node_key: str,
        *,
        depth: int = 1,
        as_of: datetime | None = None,
    ) -> TemporalKnowledgeNeighborhoodView | None:
        if depth < 1 or depth > 4:
            raise ValueError("depth must be between 1 and 4")
        async with self._session_factory() as session:
            if await session.get(EventModel, event_id) is None:
                return None
            nodes = list((await session.scalars(select(TemporalKnowledgeNodeModel).where(TemporalKnowledgeNodeModel.event_id == event_id))).all())
            edges = list((await session.scalars(select(TemporalKnowledgeEdgeModel).where(TemporalKnowledgeEdgeModel.event_id == event_id))).all())
        if as_of is not None:
            nodes = [item for item in nodes if _visible(item, as_of)]
            visible = {item.node_key for item in nodes}
            edges = [item for item in edges if item.source_key in visible and item.target_key in visible and _visible(item, as_of)]
        node_by_key = {item.node_key: item for item in nodes}
        if node_key not in node_by_key:
            raise ValueError("center node was not found in the requested historical state")
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            adjacency[edge.source_key].add(edge.target_key)
            adjacency[edge.target_key].add(edge.source_key)
        visited = {node_key}
        queue = deque([(node_key, 0)])
        while queue:
            current, level = queue.popleft()
            if level >= depth:
                continue
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1))
        selected_nodes = [node_by_key[key] for key in sorted(visited) if key in node_by_key]
        selected_edges = [edge for edge in edges if edge.source_key in visited and edge.target_key in visited]
        return TemporalKnowledgeNeighborhoodView(
            event_id=event_id,
            center_node_key=node_key,
            depth=depth,
            as_of=as_of,
            nodes=[_node_view(item) for item in selected_nodes],
            edges=[_edge_view(item) for item in selected_edges],
            generated_at=datetime.now(UTC),
            interpretation=(
                "Neighborhood traversal follows stored provenance relations only and respects the as-of visibility window. "
                "Graph proximity is contextual connectivity, not evidence that two claims imply one another."
            ),
        )


def _required_classes(run: EvidenceSearchRunModel) -> list[str]:
    requirements = run.plan.get("requirements") if isinstance(run.plan, dict) else None
    values: list[str] = []
    if isinstance(requirements, list):
        for item in requirements:
            if isinstance(item, dict):
                value = item.get("evidence_class")
                if isinstance(value, str) and value not in values:
                    values.append(value)
    return values


def _orchestration_view(model: EvidenceOrchestrationRunModel, execution) -> EvidenceOrchestrationView:
    selections = []
    raw = model.metadata_.get("selections") if isinstance(model.metadata_, dict) else None
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                selections.append(
                    EvidenceAuthoritySelectionView(
                        authority_id=UUID(str(item.get("authority_id"))),
                        evidence_class=str(item.get("evidence_class") or ""),
                        score=float(item.get("score") or 0.0),
                        reason=str(item.get("reason") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
    return EvidenceOrchestrationView(
        orchestration_id=model.id,
        claim_id=model.claim_id,
        run_id=model.search_run_id,
        orchestration_version=model.orchestration_version,
        required_evidence_classes=list(model.required_evidence_classes),
        selections=selections,
        uncovered_evidence_classes=list(model.uncovered_evidence_classes),
        coverage_ratio=model.coverage_ratio,
        status=model.status,
        execution=execution,
        metadata=model.metadata_,
        created_at=model.created_at,
        updated_at=model.updated_at,
        interpretation=str(model.metadata_.get("interpretation") or ""),
    )


def _conflict_view(model: ClaimConflictResolutionModel) -> ConflictResolutionView:
    return ConflictResolutionView(
        id=model.id,
        claim_id=model.claim_id,
        resolver_version=model.resolver_version,
        state=model.state,
        confidence=model.confidence,
        support_weight=model.support_weight,
        contradiction_weight=model.contradiction_weight,
        dispute_weight=model.dispute_weight,
        temporal_update_weight=model.temporal_update_weight,
        independent_lineage_count=model.independent_lineage_count,
        primary_support=model.primary_support,
        primary_contradiction=model.primary_contradiction,
        rationale=str(model.metadata_.get("rationale") or ""),
        metadata=model.metadata_,
        created_at=model.created_at,
    )


def _benchmark_view(model: VerificationBenchmarkEvaluationModel) -> VerificationBenchmarkEvaluationView:
    return VerificationBenchmarkEvaluationView(
        id=model.id,
        benchmark_set=model.benchmark_set,
        methodology_version=model.methodology_version,
        observation_count=model.observation_count,
        effective_weight=model.effective_weight,
        accuracy=model.accuracy,
        macro_precision=model.macro_precision,
        macro_recall=model.macro_recall,
        macro_f1=model.macro_f1,
        high_confidence_error_rate=model.high_confidence_error_rate,
        decision_weight=(model.metadata_.get("decision_metrics") or {}).get("decision_weight"),
        decision_coverage=(model.metadata_.get("decision_metrics") or {}).get("decision_coverage"),
        abstention_rate=(model.metadata_.get("decision_metrics") or {}).get("abstention_rate"),
        decided_accuracy=(model.metadata_.get("decision_metrics") or {}).get("decided_accuracy"),
        decided_macro_f1=(model.metadata_.get("decision_metrics") or {}).get("decided_macro_f1"),
        unsafe_high_confidence_error_rate=(model.metadata_.get("decision_metrics") or {}).get("unsafe_high_confidence_error_rate"),
        per_label=[BenchmarkLabelMetricsView(**item) for item in model.per_label],
        confusion_matrix=model.confusion_matrix,
        selective_metrics=[BenchmarkSelectiveMetricsView(**item) for item in model.selective_metrics],
        metadata=model.metadata_,
        created_at=model.created_at,
        interpretation=str(model.metadata_.get("interpretation") or ""),
    )


def _external_id_view(model: EntityExternalIdentifierModel) -> EntityExternalIdentifierView:
    return EntityExternalIdentifierView(
        id=model.id,
        entity_id=model.entity_id,
        namespace=model.namespace,
        external_id=model.external_id,
        canonical_url=model.canonical_url,
        provenance_url=model.provenance_url,
        confidence=model.confidence,
        verified_at=model.verified_at,
        metadata=model.metadata_,
        created_at=model.created_at,
        updated_at=model.updated_at,
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


def _visible(item, as_of: datetime) -> bool:
    value = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
    if item.observed_at > value:
        return False
    if item.valid_from is not None and item.valid_from > value:
        return False
    if item.valid_to is not None and item.valid_to < value:
        return False
    return True


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
