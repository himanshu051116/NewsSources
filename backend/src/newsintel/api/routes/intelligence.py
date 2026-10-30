from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from newsintel.api.dependencies import (
    AnalystAuth,
    ClaimVerifierAuth,
    CommitmentTrackingServiceDependency,
    EvidenceIntelligenceServiceDependency,
    EvidenceRetrievalServiceDependency,
    HistoricalKnowledgeServiceDependency,
    OwnershipRegistryServiceDependency,
    EntityResolutionServiceDependency,
    VerificationCalibrationServiceDependency,
    TemporalKnowledgeSearchServiceDependency,
    PublisherReliabilityServiceDependency,
    SettingsManagerAuth,
    TemporalKnowledgeGraphServiceDependency,
    EvidenceOrchestrationServiceDependency,
    ConflictResolutionServiceDependency,
    VerificationBenchmarkServiceDependency,
    EntityExternalIdentifierServiceDependency,
    TemporalKnowledgeResearchServiceDependency,
    EvidenceSearchStoppingServiceDependency,
    CorrectionPropagationServiceDependency,
    VerificationQualityGateServiceDependency,
    EntityRegistryServiceDependency,
    OwnershipHistoryIngestServiceDependency,
    VerificationManifestServiceDependency,
    ProductionReadinessServiceDependency,
)
from newsintel.application.intelligence.dto import (
    ClaimConfidenceHistoryView,
    CommitmentDiscoveryView,
    CommitmentEvaluationExecutionView,
    CommitmentOutcomeCommand,
    CommitmentView,
    EvidenceEvaluationCommand,
    EvidenceEvaluationExecutionView,
    EvidenceHistoryView,
    EvidencePlanExecutionView,
    EvidenceSearchCompleteView,
    EvidenceSearchExecuteCommand,
    EvidenceSearchExecutionView,
    EventKnowledgeHistoryView,
    EvidenceAuthorityCreateCommand,
    EvidenceAuthorityView,
    PublisherReliabilityRecomputeCommand,
    PublisherReliabilitySnapshotView,
    TemporalKnowledgeGraphDiffView,
    TemporalKnowledgeGraphView,
    OwnershipGroupCreateCommand,
    OwnershipGroupView,
    OwnershipMembershipCreateCommand,
    OwnershipMembershipView,
    EntityResolveCommand,
    EntityResolutionView,
    EntityAliasCreateCommand,
    EntityAliasView,
    CalibrationBenchmarkBatchCommand,
    CalibrationSnapshotView,
    TemporalKnowledgeSearchView,
    EvidenceOrchestrationCommand,
    EvidenceOrchestrationView,
    ConflictResolutionView,
    VerificationBenchmarkEvaluationView,
    EntityExternalIdentifierLinkCommand,
    EntityExternalIdentifierView,
    TemporalKnowledgeNeighborhoodView,
    BenchmarkCorpusAuditView,
    AdjudicationAgreementView,
    AccuracyDiagnosticView,
    ValidationProgramView,
    OwnershipProvenanceCreateCommand,
    OwnershipProvenanceView,
    EvidenceSearchStoppingCommand,
    EvidenceSearchStoppingView,
    CorrectionRegisterCommand,
    CorrectionEventView,
    CorrectionDetectionView,
    ClaimReviewResolveCommand,
    ClaimReviewFlagView,
    QualityGateCommand,
    QualityGateView,
    EntityRegistryCreateCommand,
    EntityRegistryView,
    EntityRegistryLinkCommand,
    EntityRegistryLinkView,
    OwnershipIngestCommand,
    OwnershipIngestView,
    CorrectionDependencyPropagationView,
    VerificationManifestCreateCommand,
    VerificationManifestView,
    VerificationManifestBackfillCommand,
    VerificationManifestBackfillView,
    ProductionReadinessCommand,
    ProductionReadinessView,
)

router = APIRouter(tags=["evidence and temporal intelligence"])


@router.post("/evidence-authorities", response_model=EvidenceAuthorityView)
async def create_evidence_authority(
    command: EvidenceAuthorityCreateCommand,
    _auth: SettingsManagerAuth,
    service: EvidenceIntelligenceServiceDependency,
) -> EvidenceAuthorityView:
    return await service.create_authority(command)


@router.get("/evidence-authorities", response_model=list[EvidenceAuthorityView])
async def list_evidence_authorities(
    _auth: AnalystAuth,
    service: EvidenceIntelligenceServiceDependency,
    evidence_class: str | None = None,
) -> list[EvidenceAuthorityView]:
    return await service.list_authorities(evidence_class=evidence_class)


@router.post("/claims/{claim_id}/evidence-plan", response_model=EvidencePlanExecutionView)
async def create_evidence_plan(
    claim_id: UUID,
    _auth: ClaimVerifierAuth,
    service: EvidenceIntelligenceServiceDependency,
) -> EvidencePlanExecutionView:
    result = await service.create_plan(claim_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.post(
    "/claims/{claim_id}/evidence-search/{run_id}/execute",
    response_model=EvidenceSearchExecutionView,
)
async def execute_authority_evidence_search(
    claim_id: UUID,
    run_id: UUID,
    command: EvidenceSearchExecuteCommand,
    _auth: ClaimVerifierAuth,
    service: EvidenceRetrievalServiceDependency,
) -> EvidenceSearchExecutionView:
    try:
        result = await service.execute(claim_id, run_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="claim or evidence search run not found",
        )
    return result


@router.post(
    "/claims/{claim_id}/evidence/evaluate",
    response_model=EvidenceEvaluationExecutionView,
)
async def evaluate_claim_evidence(
    claim_id: UUID,
    command: EvidenceEvaluationCommand,
    _auth: ClaimVerifierAuth,
    service: EvidenceIntelligenceServiceDependency,
) -> EvidenceEvaluationExecutionView:
    try:
        result = await service.evaluate_evidence(claim_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.post(
    "/claims/{claim_id}/evidence-search/{run_id}/complete",
    response_model=EvidenceSearchCompleteView,
)
async def complete_evidence_search(
    claim_id: UUID,
    run_id: UUID,
    _auth: ClaimVerifierAuth,
    service: EvidenceIntelligenceServiceDependency,
) -> EvidenceSearchCompleteView:
    result = await service.complete_search(claim_id, run_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="claim or evidence search run not found",
        )
    return result


@router.get("/claims/{claim_id}/evidence-history", response_model=EvidenceHistoryView)
async def claim_evidence_history(
    claim_id: UUID,
    _auth: AnalystAuth,
    service: EvidenceIntelligenceServiceDependency,
) -> EvidenceHistoryView:
    result = await service.history(claim_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.get(
    "/historical/claims/{claim_id}/confidence-history",
    response_model=ClaimConfidenceHistoryView,
)
async def claim_confidence_history(
    claim_id: UUID,
    _auth: AnalystAuth,
    service: EvidenceIntelligenceServiceDependency,
) -> ClaimConfidenceHistoryView:
    result = await service.confidence_history(claim_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.post(
    "/historical/events/{event_id}/commitments/discover",
    response_model=CommitmentDiscoveryView,
)
async def discover_event_commitments(
    event_id: UUID,
    _auth: ClaimVerifierAuth,
    service: CommitmentTrackingServiceDependency,
) -> CommitmentDiscoveryView:
    result = await service.discover(event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result


@router.get(
    "/historical/events/{event_id}/commitments",
    response_model=list[CommitmentView],
)
async def list_event_commitments(
    event_id: UUID,
    _auth: AnalystAuth,
    service: CommitmentTrackingServiceDependency,
) -> list[CommitmentView]:
    result = await service.list_for_event(event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result


@router.post(
    "/historical/commitments/{commitment_id}/evaluate",
    response_model=CommitmentEvaluationExecutionView,
)
async def evaluate_commitment_outcome(
    commitment_id: UUID,
    command: CommitmentOutcomeCommand,
    _auth: ClaimVerifierAuth,
    service: CommitmentTrackingServiceDependency,
) -> CommitmentEvaluationExecutionView:
    result = await service.evaluate(
        commitment_id,
        evidence_url=str(command.evidence_url),
        evidence_text=command.evidence_text,
        source_claim_id=command.source_claim_id,
        observed_at=command.observed_at,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="commitment not found")
    return result


@router.post(
    "/publishers/{publisher_id}/reliability/recompute",
    response_model=PublisherReliabilitySnapshotView,
)
async def recompute_publisher_reliability(
    publisher_id: UUID,
    command: PublisherReliabilityRecomputeCommand,
    _auth: ClaimVerifierAuth,
    service: PublisherReliabilityServiceDependency,
) -> PublisherReliabilitySnapshotView:
    result = await service.recompute(publisher_id, command)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="publisher not found")
    return result


@router.get(
    "/publishers/{publisher_id}/reliability",
    response_model=list[PublisherReliabilitySnapshotView],
)
async def publisher_reliability_history(
    publisher_id: UUID,
    _auth: AnalystAuth,
    service: PublisherReliabilityServiceDependency,
    topic_key: str | None = None,
    limit: int = 50,
) -> list[PublisherReliabilitySnapshotView]:
    result = await service.history(publisher_id, topic_key=topic_key, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="publisher not found")
    return result


@router.post(
    "/historical/events/{event_id}/knowledge-graph/rebuild",
    response_model=TemporalKnowledgeGraphView,
)
async def rebuild_event_knowledge_graph(
    event_id: UUID,
    _auth: ClaimVerifierAuth,
    service: TemporalKnowledgeGraphServiceDependency,
) -> TemporalKnowledgeGraphView:
    result = await service.rebuild(event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result


@router.get(
    "/historical/events/{event_id}/knowledge-graph/diff",
    response_model=TemporalKnowledgeGraphDiffView,
)
async def diff_event_knowledge_graph(
    event_id: UUID,
    from_at: datetime,
    to_at: datetime,
    _auth: AnalystAuth,
    service: TemporalKnowledgeGraphServiceDependency,
) -> TemporalKnowledgeGraphDiffView:
    try:
        result = await service.diff(event_id, from_at=from_at, to_at=to_at)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result


@router.get(
    "/historical/events/{event_id}/knowledge-graph",
    response_model=TemporalKnowledgeGraphView,
)
async def get_event_knowledge_graph(
    event_id: UUID,
    _auth: AnalystAuth,
    service: TemporalKnowledgeGraphServiceDependency,
    as_of: datetime | None = None,
) -> TemporalKnowledgeGraphView:
    result = await service.get(event_id, as_of=as_of)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result


@router.get(
    "/historical/events/{event_id}/knowledge-snapshots",
    response_model=EventKnowledgeHistoryView,
)
async def event_knowledge_snapshots(
    event_id: UUID,
    _auth: AnalystAuth,
    service: HistoricalKnowledgeServiceDependency,
) -> EventKnowledgeHistoryView:
    result = await service.event_snapshots(event_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result


@router.get("/ownership-groups", response_model=list[OwnershipGroupView])
async def list_ownership_groups(
    _auth: AnalystAuth,
    service: OwnershipRegistryServiceDependency,
) -> list[OwnershipGroupView]:
    return await service.list_groups()


@router.post("/ownership-groups", response_model=OwnershipGroupView)
async def create_ownership_group(
    command: OwnershipGroupCreateCommand,
    _auth: SettingsManagerAuth,
    service: OwnershipRegistryServiceDependency,
) -> OwnershipGroupView:
    return await service.create_group(command)


@router.post(
    "/ownership-groups/{group_id}/publishers/{publisher_id}",
    response_model=OwnershipMembershipView,
)
async def add_publisher_ownership_membership(
    group_id: UUID,
    publisher_id: UUID,
    command: OwnershipMembershipCreateCommand,
    _auth: SettingsManagerAuth,
    service: OwnershipRegistryServiceDependency,
) -> OwnershipMembershipView:
    try:
        result = await service.add_membership(publisher_id, group_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="publisher or ownership group not found",
        )
    return result


@router.get(
    "/publishers/{publisher_id}/ownership",
    response_model=list[OwnershipMembershipView],
)
async def publisher_ownership_history(
    publisher_id: UUID,
    _auth: AnalystAuth,
    service: OwnershipRegistryServiceDependency,
) -> list[OwnershipMembershipView]:
    result = await service.memberships_for_publisher(publisher_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="publisher not found")
    return result


@router.post("/entities/resolve", response_model=EntityResolutionView)
async def resolve_canonical_entity(
    command: EntityResolveCommand,
    _auth: ClaimVerifierAuth,
    service: EntityResolutionServiceDependency,
) -> EntityResolutionView:
    return await service.resolve(command)


@router.post("/entities/{entity_id}/aliases", response_model=EntityAliasView)
async def add_canonical_entity_alias(
    entity_id: UUID,
    command: EntityAliasCreateCommand,
    _auth: ClaimVerifierAuth,
    service: EntityResolutionServiceDependency,
) -> EntityAliasView:
    result = await service.add_alias(entity_id, command)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return result


@router.post("/verification-calibration/cases")
async def add_verification_benchmark_cases(
    command: CalibrationBenchmarkBatchCommand,
    _auth: ClaimVerifierAuth,
    service: VerificationCalibrationServiceDependency,
) -> dict[str, int]:
    return {"created": await service.add_cases(command)}


@router.post(
    "/verification-calibration/{benchmark_set}/assess",
    response_model=CalibrationSnapshotView,
)
async def assess_verification_calibration(
    benchmark_set: str,
    _auth: ClaimVerifierAuth,
    service: VerificationCalibrationServiceDependency,
    bin_count: int = 10,
) -> CalibrationSnapshotView:
    try:
        return await service.assess(benchmark_set, bin_count=bin_count)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/verification-calibration/{benchmark_set}",
    response_model=list[CalibrationSnapshotView],
)
async def verification_calibration_history(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: VerificationCalibrationServiceDependency,
    limit: int = 50,
) -> list[CalibrationSnapshotView]:
    try:
        return await service.history(benchmark_set, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/historical/knowledge-graph/search",
    response_model=TemporalKnowledgeSearchView,
)
async def search_temporal_knowledge_graph(
    query: str,
    _auth: AnalystAuth,
    service: TemporalKnowledgeSearchServiceDependency,
    node_type: list[str] | None = None,
    as_of: datetime | None = None,
    limit: int = 25,
) -> TemporalKnowledgeSearchView:
    try:
        return await service.search(
            query,
            node_types=node_type,
            as_of=as_of,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.post(
    "/claims/{claim_id}/evidence-search/{run_id}/orchestrate",
    response_model=EvidenceOrchestrationView,
)
async def orchestrate_claim_evidence_search(
    claim_id: UUID,
    run_id: UUID,
    command: EvidenceOrchestrationCommand,
    _auth: ClaimVerifierAuth,
    service: EvidenceOrchestrationServiceDependency,
) -> EvidenceOrchestrationView:
    try:
        result = await service.execute(claim_id, run_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim or evidence search run not found")
    return result


@router.post(
    "/claims/{claim_id}/conflict-resolution",
    response_model=ConflictResolutionView,
)
async def resolve_claim_evidence_conflict(
    claim_id: UUID,
    _auth: ClaimVerifierAuth,
    service: ConflictResolutionServiceDependency,
) -> ConflictResolutionView:
    result = await service.resolve(claim_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.get(
    "/claims/{claim_id}/conflict-resolution",
    response_model=list[ConflictResolutionView],
)
async def claim_conflict_resolution_history(
    claim_id: UUID,
    _auth: AnalystAuth,
    service: ConflictResolutionServiceDependency,
    limit: int = 50,
) -> list[ConflictResolutionView]:
    try:
        result = await service.history(claim_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.post(
    "/verification-benchmark/{benchmark_set}/assess",
    response_model=VerificationBenchmarkEvaluationView,
)
async def assess_verification_benchmark(
    benchmark_set: str,
    _auth: ClaimVerifierAuth,
    service: VerificationBenchmarkServiceDependency,
    split: str | None = None,
    topic_key: str | None = None,
    language: str | None = None,
    jurisdiction: str | None = None,
) -> VerificationBenchmarkEvaluationView:
    return await service.assess(
        benchmark_set,
        split=split,
        topic_key=topic_key,
        language=language,
        jurisdiction=jurisdiction,
    )


@router.get(
    "/verification-benchmark/{benchmark_set}",
    response_model=list[VerificationBenchmarkEvaluationView],
)
async def verification_benchmark_history(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: VerificationBenchmarkServiceDependency,
    limit: int = 50,
) -> list[VerificationBenchmarkEvaluationView]:
    try:
        return await service.history(benchmark_set, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/verification-benchmark/{benchmark_set}/agreement",
    response_model=AdjudicationAgreementView,
)
async def verification_benchmark_agreement(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: VerificationBenchmarkServiceDependency,
) -> AdjudicationAgreementView:
    return await service.agreement(benchmark_set)




@router.get(
    "/verification-benchmark/{benchmark_set}/validation-report",
    response_model=ValidationProgramView,
)
async def verification_benchmark_validation_report(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: VerificationBenchmarkServiceDependency,
    split: str | None = "test",
    min_overall_cases: int = 30,
    min_slice_cases: int = 10,
) -> ValidationProgramView:
    if min_overall_cases < 1 or min_overall_cases > 100_000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_overall_cases must be between 1 and 100000")
    if min_slice_cases < 1 or min_slice_cases > 10_000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="min_slice_cases must be between 1 and 10000")
    return await service.validation_report(
        benchmark_set, split=split, min_overall_cases=min_overall_cases, min_slice_cases=min_slice_cases
    )

@router.post(
    "/verification-benchmark/{benchmark_set}/diagnostics",
    response_model=AccuracyDiagnosticView,
)
async def verification_benchmark_diagnostics(
    benchmark_set: str,
    _auth: ClaimVerifierAuth,
    service: VerificationBenchmarkServiceDependency,
) -> AccuracyDiagnosticView:
    return await service.diagnostics(benchmark_set)


@router.post(
    "/entities/{entity_id}/external-identifiers",
    response_model=EntityExternalIdentifierView,
)
async def link_entity_external_identifier(
    entity_id: UUID,
    command: EntityExternalIdentifierLinkCommand,
    _auth: ClaimVerifierAuth,
    service: EntityExternalIdentifierServiceDependency,
) -> EntityExternalIdentifierView:
    try:
        result = await service.link(entity_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return result


@router.get(
    "/entities/{entity_id}/external-identifiers",
    response_model=list[EntityExternalIdentifierView],
)
async def list_entity_external_identifiers(
    entity_id: UUID,
    _auth: AnalystAuth,
    service: EntityExternalIdentifierServiceDependency,
) -> list[EntityExternalIdentifierView]:
    result = await service.list(entity_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity not found")
    return result


@router.get(
    "/historical/events/{event_id}/knowledge-graph/neighborhood",
    response_model=TemporalKnowledgeNeighborhoodView,
)
async def temporal_knowledge_neighborhood(
    event_id: UUID,
    node_key: str,
    _auth: AnalystAuth,
    service: TemporalKnowledgeResearchServiceDependency,
    depth: int = 1,
    as_of: datetime | None = None,
) -> TemporalKnowledgeNeighborhoodView:
    try:
        result = await service.neighborhood(event_id, node_key, depth=depth, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return result

@router.get(
    "/verification-benchmark/{benchmark_set}/audit",
    response_model=BenchmarkCorpusAuditView,
)
async def audit_verification_benchmark_corpus(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: VerificationBenchmarkServiceDependency,
) -> BenchmarkCorpusAuditView:
    return await service.audit(benchmark_set)

@router.post(
    "/ownership-memberships/{membership_id}/provenance",
    response_model=OwnershipProvenanceView,
)
async def add_ownership_provenance(
    membership_id: UUID,
    command: OwnershipProvenanceCreateCommand,
    _auth: SettingsManagerAuth,
    service: OwnershipRegistryServiceDependency,
) -> OwnershipProvenanceView:
    try:
        result = await service.add_provenance(membership_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ownership membership not found")
    return result


@router.get(
    "/ownership-memberships/{membership_id}/provenance",
    response_model=list[OwnershipProvenanceView],
)
async def ownership_provenance_history(
    membership_id: UUID,
    _auth: AnalystAuth,
    service: OwnershipRegistryServiceDependency,
) -> list[OwnershipProvenanceView]:
    result = await service.provenance_for_membership(membership_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ownership membership not found")
    return result



@router.post(
    "/claims/{claim_id}/evidence-search/{run_id}/stopping-assessment",
    response_model=EvidenceSearchStoppingView,
)
async def assess_evidence_search_stopping(
    claim_id: UUID,
    run_id: UUID,
    command: EvidenceSearchStoppingCommand,
    _auth: ClaimVerifierAuth,
    service: EvidenceSearchStoppingServiceDependency,
) -> EvidenceSearchStoppingView:
    result = await service.assess(claim_id, run_id, command)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim or evidence search run not found")
    return result


@router.get(
    "/claims/{claim_id}/evidence-search/stopping-history",
    response_model=list[EvidenceSearchStoppingView],
)
async def evidence_search_stopping_history(
    claim_id: UUID,
    _auth: AnalystAuth,
    service: EvidenceSearchStoppingServiceDependency,
    limit: int = 50,
) -> list[EvidenceSearchStoppingView]:
    result = await service.history(claim_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.post(
    "/historical/articles/{article_id}/corrections",
    response_model=CorrectionEventView,
)
async def register_article_correction(
    article_id: UUID,
    command: CorrectionRegisterCommand,
    _auth: ClaimVerifierAuth,
    service: CorrectionPropagationServiceDependency,
) -> CorrectionEventView:
    try:
        result = await service.register(article_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article not found")
    return result


@router.get(
    "/historical/articles/{article_id}/corrections/detect",
    response_model=CorrectionDetectionView,
)
async def detect_article_correction_candidates(
    article_id: UUID,
    _auth: AnalystAuth,
    service: CorrectionPropagationServiceDependency,
) -> CorrectionDetectionView:
    result = await service.detect(article_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article not found")
    return result


@router.get(
    "/historical/articles/{article_id}/corrections",
    response_model=list[CorrectionEventView],
)
async def article_correction_history(
    article_id: UUID,
    _auth: AnalystAuth,
    service: CorrectionPropagationServiceDependency,
) -> list[CorrectionEventView]:
    result = await service.history(article_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="article not found")
    return result


@router.post(
    "/claim-review-flags/{flag_id}/resolve",
    response_model=ClaimReviewFlagView,
)
async def resolve_claim_review_flag(
    flag_id: UUID,
    command: ClaimReviewResolveCommand,
    _auth: ClaimVerifierAuth,
    service: CorrectionPropagationServiceDependency,
) -> ClaimReviewFlagView:
    result = await service.resolve_flag(flag_id, note=command.note)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim review flag not found")
    return result


@router.post(
    "/verification-benchmark/{benchmark_set}/quality-gate",
    response_model=QualityGateView,
)
async def assess_verification_quality_gate(
    benchmark_set: str,
    command: QualityGateCommand,
    _auth: ClaimVerifierAuth,
    service: VerificationQualityGateServiceDependency,
) -> QualityGateView:
    return await service.assess(benchmark_set, command)


@router.get(
    "/verification-benchmark/{benchmark_set}/quality-gate",
    response_model=list[QualityGateView],
)
async def verification_quality_gate_history(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: VerificationQualityGateServiceDependency,
    limit: int = 50,
) -> list[QualityGateView]:
    return await service.history(benchmark_set, limit=limit)


@router.post("/entity-registries", response_model=EntityRegistryView)
async def create_entity_registry(
    command: EntityRegistryCreateCommand,
    _auth: SettingsManagerAuth,
    service: EntityRegistryServiceDependency,
) -> EntityRegistryView:
    try:
        return await service.create_profile(command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/entity-registries", response_model=list[EntityRegistryView])
async def list_entity_registries(
    _auth: AnalystAuth,
    service: EntityRegistryServiceDependency,
) -> list[EntityRegistryView]:
    return await service.list_profiles()


@router.post(
    "/entities/{entity_id}/registry-link",
    response_model=EntityRegistryLinkView,
)
async def link_entity_from_registry(
    entity_id: UUID,
    command: EntityRegistryLinkCommand,
    _auth: ClaimVerifierAuth,
    service: EntityRegistryServiceDependency,
) -> EntityRegistryLinkView:
    try:
        result = await service.link(entity_id, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="entity or active registry not found")
    return result


@router.post("/ownership/ingest", response_model=OwnershipIngestView)
async def ingest_ownership_history(
    command: OwnershipIngestCommand,
    _auth: SettingsManagerAuth,
    service: OwnershipHistoryIngestServiceDependency,
) -> OwnershipIngestView:
    return await service.ingest(command)


@router.get(
    "/corrections/{correction_event_id}/dependency-propagation",
    response_model=CorrectionDependencyPropagationView,
)
async def correction_dependency_propagation(
    correction_event_id: UUID,
    _auth: AnalystAuth,
    service: CorrectionPropagationServiceDependency,
) -> CorrectionDependencyPropagationView:
    result = await service.dependency_propagation(correction_event_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="correction dependency propagation run not found",
        )
    return result


@router.post(
    "/claims/{claim_id}/verification-manifests",
    response_model=VerificationManifestView,
)
async def create_verification_manifest(
    claim_id: UUID,
    command: VerificationManifestCreateCommand,
    _auth: ClaimVerifierAuth,
    service: VerificationManifestServiceDependency,
) -> VerificationManifestView:
    result = await service.create(claim_id, verification_id=command.verification_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="claim or verification revision not found",
        )
    return result


@router.get(
    "/claims/{claim_id}/verification-manifests",
    response_model=list[VerificationManifestView],
)
async def verification_manifest_history(
    claim_id: UUID,
    _auth: AnalystAuth,
    service: VerificationManifestServiceDependency,
    limit: int = 50,
) -> list[VerificationManifestView]:
    result = await service.history(claim_id, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    return result


@router.post(
    "/verification-manifests/backfill",
    response_model=VerificationManifestBackfillView,
)
async def backfill_verification_manifests(
    command: VerificationManifestBackfillCommand,
    _auth: ClaimVerifierAuth,
    service: VerificationManifestServiceDependency,
) -> VerificationManifestBackfillView:
    return await service.backfill(command)


@router.post(
    "/system/release-readiness/{benchmark_set}",
    response_model=ProductionReadinessView,
)
async def assess_production_readiness(
    benchmark_set: str,
    command: ProductionReadinessCommand,
    _auth: SettingsManagerAuth,
    service: ProductionReadinessServiceDependency,
) -> ProductionReadinessView:
    return await service.assess(benchmark_set, command)


@router.get(
    "/system/release-readiness/{benchmark_set}",
    response_model=list[ProductionReadinessView],
)
async def production_readiness_history(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: ProductionReadinessServiceDependency,
    limit: int = 50,
) -> list[ProductionReadinessView]:
    return await service.history(benchmark_set, limit=limit)
