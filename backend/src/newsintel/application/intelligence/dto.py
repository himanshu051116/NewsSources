from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from newsintel.adapters.evidence.authority_search import AuthorityAdapterType
from newsintel.domain.intelligence.primary_evidence import EvidenceAuthorityClass
from newsintel.domain.intelligence.claims import ClaimVerificationLabel
from newsintel.domain.intelligence.entities import EntityType
from newsintel.domain.intelligence.ownership import OwnershipRelationship


class EvidenceRequirementView(BaseModel):
    evidence_class: str
    priority: int
    required: bool
    rationale: str
    query_hints: list[str]
    authority_hints: list[str]


class EvidencePlanView(BaseModel):
    planner_version: str
    claim_type: str
    claim_text: str
    plan_key: str
    requirements: list[EvidenceRequirementView]
    search_terms: list[str]
    completeness_criteria: dict[str, object]
    configured_authorities: list[dict[str, object]] = Field(default_factory=list)


class EvidenceSearchRunView(BaseModel):
    id: UUID
    claim_id: UUID
    status: str
    plan_key: str
    planner_version: str
    retrieval_complete: bool
    source_count: int
    evidence_count: int
    started_at: datetime
    completed_at: datetime | None
    plan: dict[str, object]
    metadata: dict[str, object]


class EvidencePlanExecutionView(BaseModel):
    claim_id: UUID
    run: EvidenceSearchRunView
    plan: EvidencePlanView


class EvidenceEvaluationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_url: HttpUrl
    source_type: str = Field(min_length=2, max_length=80)
    evidence_text: str = Field(min_length=2, max_length=250_000)
    evidence_class: EvidenceAuthorityClass | None = None
    search_run_id: UUID | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    independence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    primary_source: bool = False


class EvidencePassageEvaluationView(BaseModel):
    id: UUID
    claim_id: UUID
    search_run_id: UUID | None
    source_url: str
    source_type: str
    evidence_class: str | None
    passage_text: str
    passage_sha256: str
    stance: str
    stance_confidence: float
    assessor_version: str
    temporal_relation: str
    published_at: datetime | None
    retrieved_at: datetime
    independence_score: float
    primary_source: bool
    metadata: dict[str, object]
    created_at: datetime


class EvidenceEvaluationExecutionView(BaseModel):
    claim_id: UUID
    evaluation: EvidencePassageEvaluationView
    evidence_link_id: UUID | None = None


class EvidenceSearchCompleteView(BaseModel):
    claim_id: UUID
    run: EvidenceSearchRunView
    verification_label: str | None = None
    verification_confidence: float | None = None
    verification_id: UUID | None = None


class ClaimConfidenceSnapshotView(BaseModel):
    verification_id: UUID
    label: str
    confidence_score: float | None
    methodology_version: str
    created_at: datetime
    confidence_factors: dict[str, object]
    reasoning_trace: dict[str, object]


class ClaimConfidenceHistoryView(BaseModel):
    claim_id: UUID
    claim_text: str
    current_label: str | None
    current_confidence: float | None
    snapshots: list[ClaimConfidenceSnapshotView]
    generated_at: datetime
    interpretation: str


class EvidenceRetrievalAttemptView(BaseModel):
    id: UUID
    search_run_id: UUID
    authority_profile_id: UUID
    search_url: str | None
    candidate_url: str | None
    status: str
    http_status: int | None
    body_sha256: str | None
    error_type: str | None
    error_message: str | None
    metadata: dict[str, object]
    created_at: datetime


class EvidenceHistoryView(BaseModel):
    claim_id: UUID
    runs: list[EvidenceSearchRunView]
    evaluations: list[EvidencePassageEvaluationView]
    retrieval_attempts: list[EvidenceRetrievalAttemptView] = Field(default_factory=list)
    confidence_history: ClaimConfidenceHistoryView


class CommitmentView(BaseModel):
    id: UUID
    event_id: UUID
    source_claim_id: UUID
    commitment_key: str
    commitment_type: str
    commitment_text: str
    actor: str | None
    deadline_text: str | None
    deadline_at: datetime | None
    status: str
    first_observed_at: datetime
    last_evaluated_at: datetime | None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


class CommitmentDiscoveryView(BaseModel):
    event_id: UUID
    discovered_count: int
    total_count: int
    commitments: list[CommitmentView]


class CommitmentOutcomeCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    evidence_url: HttpUrl
    evidence_text: str = Field(min_length=2, max_length=250_000)
    source_claim_id: UUID | None = None
    observed_at: datetime | None = None


class CommitmentOutcomeView(BaseModel):
    id: UUID
    commitment_id: UUID
    source_claim_id: UUID | None
    evidence_url: str
    status: str
    confidence: float
    tracker_version: str
    observed_at: datetime
    reasoning: str
    metadata: dict[str, object]
    created_at: datetime


class CommitmentEvaluationExecutionView(BaseModel):
    commitment: CommitmentView
    outcome: CommitmentOutcomeView

class EventKnowledgeSnapshotView(BaseModel):
    snapshot_at: datetime
    article_version_count: int
    publisher_count: int
    known_claim_count: int
    verification_counts: dict[str, int]
    average_verification_confidence: float | None
    commitment_status_counts: dict[str, int]
    evidence_state: str = "as_known_then"


class EventKnowledgeHistoryView(BaseModel):
    event_id: UUID
    title: str
    snapshot_basis: str
    interpretation: str
    snapshots: list[EventKnowledgeSnapshotView]
    generated_at: datetime

class EvidenceAuthorityCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=240)
    evidence_class: EvidenceAuthorityClass
    jurisdiction: str = Field(default="global", min_length=2, max_length=120)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    base_url: HttpUrl
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)
    search_url_template: str | None = Field(default=None, max_length=2000)
    adapter_type: AuthorityAdapterType = AuthorityAdapterType.GENERIC_HTML_SEARCH
    adapter_config: dict[str, object] = Field(default_factory=dict)
    trust_scope: dict[str, object] = Field(default_factory=dict)


class EvidenceAuthorityView(BaseModel):
    id: UUID
    name: str
    evidence_class: str
    jurisdiction: str
    language: str | None
    base_url: str
    allowed_domains: list[str]
    search_url_template: str | None
    adapter_type: str
    adapter_config: dict[str, object]
    trust_scope: dict[str, object]
    active: bool
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


class EvidenceSearchExecuteCommand(BaseModel):
    authority_ids: list[UUID] = Field(default_factory=list, max_length=20)
    max_authorities: int = Field(default=5, ge=1, le=20)
    max_candidates_per_authority: int = Field(default=3, ge=1, le=10)
    query_override: str | None = Field(default=None, min_length=2, max_length=500)


class EvidenceAuthorityExecutionView(BaseModel):
    authority_id: UUID
    authority_name: str
    evidence_class: str
    documents_retrieved: int
    evaluations_created: int
    attempts: list[EvidenceRetrievalAttemptView]


class EvidenceSearchExecutionView(BaseModel):
    claim_id: UUID
    run_id: UUID
    authorities_attempted: int
    documents_retrieved: int
    evaluations_created: int
    authority_results: list[EvidenceAuthorityExecutionView]
    guardrail: str


class PublisherReliabilityRecomputeCommand(BaseModel):
    lookback_days: int = Field(default=180, ge=1, le=3650)
    topic_key: str | None = Field(default=None, min_length=2, max_length=80)
    prior_alpha: float = Field(default=2.0, gt=0, le=100)
    prior_beta: float = Field(default=2.0, gt=0, le=100)


class PublisherReliabilitySnapshotView(BaseModel):
    id: UUID
    publisher_id: UUID
    publisher_name: str
    topic_key: str
    methodology_version: str
    window_start: datetime
    window_end: datetime
    posterior_mean: float | None
    interval_low: float | None
    interval_high: float | None
    effective_successes: float
    effective_failures: float
    effective_sample_size: float
    raw_observation_count: int
    excluded_observation_count: int
    prior_alpha: float
    prior_beta: float
    interpretation: str
    metadata: dict[str, object]
    created_at: datetime


class TemporalKnowledgeNodeView(BaseModel):
    node_key: str
    node_type: str
    label: str
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    payload: dict[str, object]


class TemporalKnowledgeEdgeView(BaseModel):
    edge_key: str
    source_key: str
    target_key: str
    relation: str
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    payload: dict[str, object]


class TemporalKnowledgeGraphView(BaseModel):
    event_id: UUID
    event_title: str
    graph_version: str
    as_of: datetime | None
    node_count: int
    edge_count: int
    nodes: list[TemporalKnowledgeNodeView]
    edges: list[TemporalKnowledgeEdgeView]
    generated_at: datetime
    interpretation: str

class TemporalKnowledgeGraphDiffView(BaseModel):
    event_id: UUID
    from_at: datetime
    to_at: datetime
    added_nodes: list[TemporalKnowledgeNodeView]
    expired_nodes: list[TemporalKnowledgeNodeView]
    added_edges: list[TemporalKnowledgeEdgeView]
    expired_edges: list[TemporalKnowledgeEdgeView]
    summary: dict[str, int]
    generated_at: datetime
    interpretation: str


class OwnershipGroupCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=300)
    canonical_domain: str | None = Field(default=None, max_length=253)
    jurisdiction: str | None = Field(default=None, max_length=120)
    metadata: dict[str, object] = Field(default_factory=dict)


class OwnershipGroupView(BaseModel):
    id: UUID
    name: str
    canonical_domain: str | None
    jurisdiction: str | None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


class OwnershipMembershipCreateCommand(BaseModel):
    relationship: OwnershipRelationship
    ownership_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    provenance_url: HttpUrl | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class OwnershipMembershipView(BaseModel):
    id: UUID
    publisher_id: UUID
    group_id: UUID
    group_name: str
    relationship: str
    ownership_fraction: float | None
    valid_from: datetime | None
    valid_to: datetime | None
    provenance_url: str | None
    confidence: float
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


class EntityResolveCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=500)
    entity_type: EntityType = EntityType.OTHER
    country_code: str | None = Field(default=None, min_length=2, max_length=8)
    external_ids: dict[str, str] = Field(default_factory=dict)
    create_if_unmatched: bool = False


class EntityResolutionView(BaseModel):
    entity_id: UUID | None
    entity_key: str | None
    canonical_name: str | None
    entity_type: str
    confidence: float
    match_basis: str
    normalized_candidate: str
    ambiguous: bool
    created: bool = False


class CalibrationBenchmarkCaseCommand(BaseModel):
    claim_id: UUID | None = None
    benchmark_set: str = Field(min_length=2, max_length=120)
    case_key: str | None = Field(default=None, min_length=2, max_length=160)
    group_key: str | None = Field(default=None, min_length=2, max_length=180)
    source_document_key: str | None = Field(default=None, min_length=2, max_length=180)
    split: str = Field(default="unspecified", min_length=2, max_length=40)
    topic_key: str | None = Field(default=None, min_length=2, max_length=80)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    jurisdiction: str | None = Field(default=None, min_length=2, max_length=120)
    predicted_label: ClaimVerificationLabel
    predicted_confidence: float = Field(ge=0.0, le=1.0)
    adjudicated_label: ClaimVerificationLabel
    adjudication_source: str = Field(min_length=2, max_length=200)
    adjudicator_count: int = Field(default=1, ge=1, le=100)
    adjudicated_at: datetime | None = None
    weight: float = Field(default=1.0, gt=0.0, le=100.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class CalibrationBenchmarkBatchCommand(BaseModel):
    cases: list[CalibrationBenchmarkCaseCommand] = Field(min_length=1, max_length=500)


class CalibrationBinView(BaseModel):
    lower: float
    upper: float
    count: int
    weight: float
    mean_confidence: float | None
    empirical_accuracy: float | None
    calibration_gap: float | None


class CalibrationSnapshotView(BaseModel):
    id: UUID
    benchmark_set: str
    methodology_version: str
    observation_count: int
    effective_weight: float
    brier_score: float | None
    expected_calibration_error: float | None
    mean_confidence: float | None
    empirical_accuracy: float | None
    bins: list[CalibrationBinView]
    interpretation: str
    metadata: dict[str, object]
    created_at: datetime


class TemporalKnowledgeSearchHitView(BaseModel):
    event_id: UUID
    node_key: str
    node_type: str
    label: str
    score: float
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    payload: dict[str, object]


class TemporalKnowledgeSearchView(BaseModel):
    query: str
    as_of: datetime | None
    node_types: list[str]
    hits: list[TemporalKnowledgeSearchHitView]
    generated_at: datetime
    interpretation: str


class EntityAliasCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    alias: str = Field(min_length=1, max_length=500)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    source: str = Field(default="analyst", min_length=2, max_length=80)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class EntityAliasView(BaseModel):
    id: UUID
    entity_id: UUID
    alias: str
    normalized_alias: str
    language: str | None
    source: str
    confidence: float
    created_at: datetime


class EvidenceOrchestrationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    jurisdiction: str | None = Field(default=None, min_length=2, max_length=120)
    language: str | None = Field(default=None, min_length=2, max_length=35)
    max_authorities: int = Field(default=5, ge=1, le=20)
    max_candidates_per_authority: int = Field(default=3, ge=1, le=10)
    query_override: str | None = Field(default=None, min_length=2, max_length=500)


class EvidenceAuthoritySelectionView(BaseModel):
    authority_id: UUID
    evidence_class: str
    score: float
    reason: str


class EvidenceOrchestrationView(BaseModel):
    orchestration_id: UUID
    claim_id: UUID
    run_id: UUID
    orchestration_version: str
    required_evidence_classes: list[str]
    selections: list[EvidenceAuthoritySelectionView]
    uncovered_evidence_classes: list[str]
    coverage_ratio: float
    status: str
    execution: EvidenceSearchExecutionView | None = None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    interpretation: str


class ConflictResolutionView(BaseModel):
    id: UUID
    claim_id: UUID
    resolver_version: str
    state: str
    confidence: float
    support_weight: float
    contradiction_weight: float
    dispute_weight: float
    temporal_update_weight: float
    independent_lineage_count: int
    primary_support: bool
    primary_contradiction: bool
    rationale: str
    metadata: dict[str, object]
    created_at: datetime


class BenchmarkLabelMetricsView(BaseModel):
    label: str
    support: float
    precision: float | None
    recall: float | None
    f1: float | None


class BenchmarkSelectiveMetricsView(BaseModel):
    threshold: float
    coverage: float
    accuracy: float | None
    error_rate: float | None
    selected_weight: float


class VerificationBenchmarkEvaluationView(BaseModel):
    id: UUID
    benchmark_set: str
    methodology_version: str
    observation_count: int
    effective_weight: float
    accuracy: float | None
    macro_precision: float | None
    macro_recall: float | None
    macro_f1: float | None
    high_confidence_error_rate: float | None
    decision_weight: float | None = None
    decision_coverage: float | None = None
    abstention_rate: float | None = None
    decided_accuracy: float | None = None
    decided_macro_f1: float | None = None
    unsafe_high_confidence_error_rate: float | None = None
    per_label: list[BenchmarkLabelMetricsView]
    confusion_matrix: dict[str, dict[str, float]]
    selective_metrics: list[BenchmarkSelectiveMetricsView]
    metadata: dict[str, object]
    created_at: datetime
    interpretation: str


class EntityExternalIdentifierLinkCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    namespace: str = Field(min_length=2, max_length=80)
    external_id: str = Field(min_length=1, max_length=300)
    canonical_url: HttpUrl | None = None
    provenance_url: HttpUrl | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class EntityExternalIdentifierView(BaseModel):
    id: UUID
    entity_id: UUID
    namespace: str
    external_id: str
    canonical_url: str | None
    provenance_url: str | None
    confidence: float
    verified_at: datetime | None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


class TemporalKnowledgeNeighborhoodView(BaseModel):
    event_id: UUID
    center_node_key: str
    depth: int
    as_of: datetime | None
    nodes: list[TemporalKnowledgeNodeView]
    edges: list[TemporalKnowledgeEdgeView]
    generated_at: datetime
    interpretation: str


class BenchmarkCorpusAuditView(BaseModel):
    benchmark_set: str
    audit_version: str
    case_count: int
    effective_weight: float
    split_counts: dict[str, int]
    label_counts: dict[str, int]
    topic_counts: dict[str, int]
    language_counts: dict[str, int]
    jurisdiction_counts: dict[str, int]
    leakage_keys: list[str]
    leakage_case_count: int
    duplicate_within_split_keys: list[str]
    group_leakage_keys: list[str] = Field(default_factory=list)
    source_document_leakage_keys: list[str] = Field(default_factory=list)
    single_adjudicator_ratio: float | None
    readiness: str
    warnings: list[str]
    interpretation: str
    generated_at: datetime


class OwnershipProvenanceCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_url: HttpUrl
    source_type: str = Field(min_length=2, max_length=80)
    passage_text: str | None = Field(default=None, max_length=250_000)
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class OwnershipProvenanceView(BaseModel):
    id: UUID
    membership_id: UUID
    source_url: str
    source_type: str
    passage_text: str | None
    passage_sha256: str | None
    observed_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    confidence: float
    metadata: dict[str, object]
    created_at: datetime


class EvidenceSearchStoppingCommand(BaseModel):
    max_rounds: int = Field(default=4, ge=1, le=20)
    min_independent_lineages: int = Field(default=2, ge=0, le=20)
    require_primary_record: bool = True


class EvidenceSearchStoppingView(BaseModel):
    id: UUID
    claim_id: UUID
    run_id: UUID
    methodology_version: str
    decision: str
    completeness_score: float
    covered_evidence_classes: list[str]
    uncovered_evidence_classes: list[str]
    independent_lineages: int
    primary_records: int
    rounds_completed: int
    rationale: str
    metadata: dict[str, object]
    created_at: datetime


class CorrectionRegisterCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    correction_kind: str = Field(min_length=3, max_length=60)
    article_version_id: UUID | None = None
    source_url: HttpUrl | None = None
    note: str | None = Field(default=None, max_length=20_000)
    affected_claim_ids: list[UUID] = Field(default_factory=list, max_length=500)
    propagate_dependencies: bool = True
    max_dependency_depth: int = Field(default=2, ge=1, le=5)
    max_dependency_claims: int = Field(default=500, ge=1, le=2_000)


class ClaimReviewFlagView(BaseModel):
    id: UUID
    correction_event_id: UUID
    claim_id: UUID
    state: str
    severity: str
    actions: list[str]
    reason: str
    resolved_at: datetime | None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


class CorrectionEventView(BaseModel):
    id: UUID
    article_id: UUID
    article_version_id: UUID | None
    event_id: UUID
    correction_kind: str
    source_url: str | None
    note: str | None
    affected_claim_ids: list[UUID]
    propagation_plan: dict[str, object]
    review_flags: list[ClaimReviewFlagView]
    created_at: datetime
    interpretation: str


class QualityGateCommand(BaseModel):
    min_cases: int = Field(default=100, ge=1, le=1_000_000)
    min_test_cases: int = Field(default=30, ge=1, le=1_000_000)
    min_macro_f1: float = Field(default=0.75, ge=0.0, le=1.0)
    max_high_confidence_error_rate: float = Field(default=0.08, ge=0.0, le=1.0)
    min_selective_accuracy_80: float = Field(default=0.85, ge=0.0, le=1.0)
    min_selective_coverage_80: float = Field(default=0.35, ge=0.0, le=1.0)
    min_decision_coverage: float = Field(default=0.40, ge=0.0, le=1.0)
    min_decided_accuracy: float = Field(default=0.80, ge=0.0, le=1.0)
    max_unsafe_high_confidence_error_rate: float = Field(default=0.10, ge=0.0, le=1.0)


class QualityGateView(BaseModel):
    id: UUID
    benchmark_set: str
    evaluation_id: UUID | None
    methodology_version: str
    state: str
    failures: list[str]
    warnings: list[str]
    thresholds: dict[str, object]
    metrics: dict[str, object]
    metadata: dict[str, object]
    created_at: datetime
    interpretation: str


class EntityRegistryCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=200)
    namespace: str = Field(min_length=2, max_length=80)
    base_url: HttpUrl
    search_url_template: str = Field(min_length=10, max_length=2_000)
    entity_type: str | None = Field(default=None, max_length=80)
    jurisdiction: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=35)
    adapter_type: str = Field(default="configured_json", max_length=80)
    config: dict[str, object] = Field(default_factory=dict)
    active: bool = True


class EntityRegistryView(BaseModel):
    id: UUID
    name: str
    namespace: str
    base_url: str
    search_url_template: str
    entity_type: str | None
    jurisdiction: str | None
    language: str | None
    adapter_type: str
    config: dict[str, object]
    active: bool
    created_at: datetime
    updated_at: datetime


class EntityRegistryLinkCommand(BaseModel):
    registry_profile_id: UUID
    max_results: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    ambiguity_margin: float = Field(default=0.08, ge=0.0, le=0.5)
    persist_match: bool = False


class EntityRegistryCandidateView(BaseModel):
    external_id: str
    label: str
    score: float
    canonical_url: str | None
    reasons: list[str]


class EntityRegistryLinkView(BaseModel):
    id: UUID
    entity_id: UUID
    registry_profile_id: UUID
    methodology_version: str
    state: str
    selected_external_id: str | None
    selected_score: float | None
    candidates: list[EntityRegistryCandidateView]
    search_url: str | None
    response_sha256: str | None
    linked_identifier_id: UUID | None = None
    metadata: dict[str, object]
    created_at: datetime
    interpretation: str


class OwnershipIngestItemCommand(BaseModel):
    publisher_id: UUID
    group_id: UUID
    relationship: OwnershipRelationship
    ownership_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_url: HttpUrl
    source_type: str = Field(min_length=2, max_length=80)
    passage_text: str | None = Field(default=None, max_length=250_000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class OwnershipIngestCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_name: str = Field(min_length=2, max_length=200)
    source_url: HttpUrl | None = None
    observed_at: datetime | None = None
    items: list[OwnershipIngestItemCommand] = Field(min_length=1, max_length=2_000)


class OwnershipIngestView(BaseModel):
    id: UUID
    source_name: str
    source_url: str | None
    observed_at: datetime
    input_count: int
    membership_created_count: int
    provenance_created_count: int
    rejected_count: int
    rejected_items: list[dict[str, object]]
    created_at: datetime
    interpretation: str


class ClaimReviewResolveCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    note: str | None = Field(default=None, max_length=10_000)


class CorrectionCandidateView(BaseModel):
    from_version_id: UUID
    to_version_id: UUID
    from_version_number: int
    to_version_number: int
    suggested_kind: str
    confidence: float
    reason: str
    material_change_count: int
    numeric_change_count: int
    temporal_change_count: int
    requires_human_confirmation: bool


class CorrectionDetectionView(BaseModel):
    article_id: UUID
    methodology_version: str
    candidates: list[CorrectionCandidateView]
    generated_at: datetime
    interpretation: str


class CorrectionDependencyImpactView(BaseModel):
    claim_id: UUID
    claim_article_id: UUID
    via_article_id: UUID
    depth: int
    severity: str
    actions: list[str]
    rationale: str


class CorrectionDependencyPropagationView(BaseModel):
    id: UUID
    correction_event_id: UUID
    root_article_id: UUID
    methodology_version: str
    correction_kind: str
    max_depth: int
    direct_dependency_count: int
    indirect_dependency_count: int
    truncated: bool
    impacts: list[CorrectionDependencyImpactView]
    metadata: dict[str, object]
    created_at: datetime


class VerificationManifestCreateCommand(BaseModel):
    verification_id: UUID | None = None


class VerificationManifestView(BaseModel):
    id: UUID
    claim_id: UUID
    verification_id: UUID
    manifest_version: str
    manifest_sha256: str
    code_version: str
    claim_sha256: str
    article_content_sha256: str
    evidence_snapshot: list[dict[str, object]]
    authority_snapshot: list[dict[str, object]]
    decision_context: dict[str, object]
    payload: dict[str, object]
    created_at: datetime
    interpretation: str


class ProductionReadinessCommand(BaseModel):
    min_manifest_coverage: float = Field(default=0.8, ge=0, le=1)
    max_open_critical_reviews: int = Field(default=0, ge=0, le=10_000)
    require_quality_gate_pass: bool = True
    require_active_authority: bool = True
    verification_sample_size: int = Field(default=100, ge=1, le=10_000)


class ProductionReadinessView(BaseModel):
    id: UUID
    benchmark_set: str
    methodology_version: str
    state: str
    failures: list[str]
    warnings: list[str]
    checks: dict[str, object]
    thresholds: dict[str, object]
    metadata: dict[str, object]
    created_at: datetime
    interpretation: str


class VerificationManifestBackfillCommand(BaseModel):
    limit: int = Field(default=500, ge=1, le=10_000)


class VerificationManifestBackfillView(BaseModel):
    requested_limit: int
    candidates: int
    created: int
    failed: int
    failures: list[dict[str, str]]
    interpretation: str

class AdjudicationAgreementView(BaseModel):
    benchmark_set: str
    methodology_version: str
    case_count: int
    review_count: int
    multi_review_case_count: int
    unanimous_case_count: int
    disagreement_case_count: int
    adjudicated_disagreement_count: int
    pairwise_agreement: float | None
    krippendorff_alpha_nominal: float | None
    label_counts: dict[str, int]
    reviewer_counts: dict[str, int]
    interpretation: str
    generated_at: datetime




class ValidationConfidenceIntervalView(BaseModel):
    estimate: float | None
    lower: float | None
    upper: float | None
    sample_size: int


class ValidationSliceView(BaseModel):
    dimension: str
    value: str
    case_count: int
    decision_count: int
    decision_coverage: float
    decided_accuracy: float | None
    accuracy_interval: ValidationConfidenceIntervalView
    unsafe_high_confidence_error_rate: float | None
    gate_state: str
    failures: list[str]


class ActiveSamplingTargetView(BaseModel):
    dimension: str
    value: str
    priority: float
    reason: str
    case_count: int


class ValidationProgramView(BaseModel):
    benchmark_set: str
    methodology_version: str
    corpus_fingerprint: str
    corpus_case_count: int
    decided_case_count: int
    decision_coverage: float
    decided_accuracy: float | None
    decided_accuracy_interval: ValidationConfidenceIntervalView
    unsafe_high_confidence_error_rate: float | None
    overall_gate_state: str
    failures: list[str]
    slice_results: list[ValidationSliceView]
    active_sampling_targets: list[ActiveSamplingTargetView]
    generated_at: datetime
    interpretation: str

class AccuracyDiagnosticView(BaseModel):
    benchmark_set: str
    methodology_version: str
    case_count: int
    error_count: int
    error_rate: float
    taxonomy_counts: dict[str, int]
    topic_error_rates: dict[str, float]
    language_error_rates: dict[str, float]
    source_error_rates: dict[str, float]
    high_confidence_error_count: int
    interpretation: str
    generated_at: datetime
