from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ArticleVersionView(BaseModel):
    id: UUID
    version_number: int
    source_url: str
    final_url: str
    title: str
    byline: str | None
    language: str | None
    published_at: datetime | None
    retrieved_at: datetime
    content_sha256: str
    extraction_method: str
    extraction_warnings: list[str]
    extraction_quality_score: float | None
    extraction_fidelity_score: float | None = None
    extraction_fidelity_label: str | None = None
    extraction_fidelity_discrepancies: list[str] = Field(default_factory=list)
    browser_rendered: bool = False
    raw_artifact_uri: str | None
    document_pages: list[dict[str, object]] = Field(default_factory=list)
    document_table_candidates: list[dict[str, object]] = Field(default_factory=list)
    document_table_review_required: bool = False
    document_page_count: int | None = None
    document_truncated: bool = False
    word_count: int
    text_content: str
    created_at: datetime


class ArticleSummaryView(BaseModel):
    id: UUID
    event_id: UUID
    publisher_id: UUID
    canonical_url: str
    title: str
    language: str | None
    published_at: datetime | None
    first_observed_at: datetime
    latest_version_id: UUID | None
    latest_version_number: int | None
    latest_extraction_method: str | None
    latest_extraction_warnings: list[str]
    latest_extraction_quality_score: float | None
    latest_extraction_fidelity_score: float | None = None
    latest_extraction_fidelity_label: str | None = None
    word_count: int | None
    historical_context_status: str | None = None
    historical_depth: str | None = None
    historical_confidence_score: float | None = None
    historical_change_pattern: str | None = None




class ArticleHistoricalContextView(BaseModel):
    article_id: UUID
    article_version_id: UUID
    event_id: UUID
    methodology_version: str
    status: str
    cutoff_at: datetime
    queries: list[str]
    same_event_history: list[dict[str, object]]
    prior_claim_history: list[dict[str, object]]
    internal_matches: list[dict[str, object]]
    external_matches: list[dict[str, object]]
    provider_statuses: list[dict[str, object]]
    timeline_summary: dict[str, object]
    context_summary: dict[str, object]
    generated_at: datetime


class HistoricalEnrichmentStateView(BaseModel):
    state: str
    attempt_count: int
    refresh_count: int = 0
    last_refresh_reason: str | None = None
    last_reconciled_at: datetime | None = None
    last_error: str | None
    next_attempt_at: datetime | None
    updated_at: datetime


class ArticleDetailView(BaseModel):
    id: UUID
    event_id: UUID
    publisher_id: UUID
    canonical_url: str
    title: str
    language: str | None
    published_at: datetime | None
    first_observed_at: datetime
    created_at: datetime
    updated_at: datetime
    latest_version: ArticleVersionView | None
    historical_context: ArticleHistoricalContextView | None = None
    historical_enrichment: HistoricalEnrichmentStateView | None = None




class ArticleIntelligenceStateView(BaseModel):
    article_id: UUID
    state: str
    historical_state: str | None = None
    historical_depth: str | None = None
    historical_change_pattern: str | None = None
    extraction_warning_count: int = 0
    review_required_claim_count: int = 0
    critical_review_claim_count: int = 0
    updated_at: datetime

class EventSummaryView(BaseModel):
    id: UUID
    slug: str
    title: str
    lifecycle_status: str
    assignment_status: str
    first_detected_at: datetime
    last_material_change_at: datetime
    article_count: int
    publisher_count: int


class EventDetailView(BaseModel):
    id: UUID
    slug: str
    title: str
    lifecycle_status: str
    assignment_status: str
    first_detected_at: datetime
    last_material_change_at: datetime
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    articles: list[ArticleSummaryView]


class EvidenceLineageSummaryView(BaseModel):
    lineage_key: str
    link_count: int = 0
    claim_count: int = 0
    source_count: int = 0
    source_urls: list[str] = Field(default_factory=list)
    max_independence_score: float = 0.0
    primary_source_present: bool = False
    shared_ownership_present: bool = False
    circular_sourcing_present: bool = False
    relationships: list[str] = Field(default_factory=list)


class EventDossierClaimView(BaseModel):
    id: UUID
    article_id: UUID
    article_title: str
    claim_text: str
    claim_type: str | None = None
    verification_label: str | None = None
    verification_confidence: float | None = None
    evidence_link_count: int = 0
    independent_evidence_count: int = 0
    independent_lineage_count: int = 0
    primary_evidence_count: int = 0
    contradiction_evidence_count: int = 0
    ownership_reduced_evidence_count: int = 0
    circular_sourcing_count: int = 0
    near_duplicate_evidence_count: int = 0
    same_lineage_duplicate_count: int = 0


class EventPublisherBreakdownView(BaseModel):
    publisher_id: UUID
    publisher_name: str
    article_count: int


class EventDossierView(BaseModel):
    event: EventDetailView
    latest_claim_count: int
    verified_claim_count: int
    unresolved_claim_count: int
    independent_evidence_link_count: int
    independent_lineage_count: int = 0
    primary_evidence_link_count: int
    contradiction_evidence_link_count: int
    ownership_reduced_evidence_link_count: int = 0
    circular_sourcing_link_count: int = 0
    near_duplicate_evidence_link_count: int = 0
    verification_counts: dict[str, int] = Field(default_factory=dict)
    publisher_breakdown: list[EventPublisherBreakdownView] = Field(default_factory=list)
    lineage_breakdown: list[EvidenceLineageSummaryView] = Field(default_factory=list)
    claims: list[EventDossierClaimView] = Field(default_factory=list)


class IntelligenceSearchResultView(BaseModel):
    result_type: str
    id: UUID
    title: str
    snippet: str | None = None
    event_id: UUID | None = None
    article_id: UUID | None = None
    occurred_at: datetime | None = None
    score: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class IntelligenceSearchView(BaseModel):
    query: str
    results: list[IntelligenceSearchResultView]
    counts: dict[str, int] = Field(default_factory=dict)
    searched_claims: bool = False
    searched_entities: bool = False
    next_cursor: str | None = None
    snapshot_at: datetime | None = None
    search_mode: str = "postgres_fts"
    filters: dict[str, object] = Field(default_factory=dict)
    deployment_variant: str = "lexical"
    deployment_exposure_id: UUID | None = None
    deployment_bucket: int | None = None


class ClaimEvidenceLinkView(BaseModel):
    id: UUID
    source_url: str
    source_type: str
    relationship: str
    retrieved_at: datetime
    similarity_score: float | None
    independence_score: float
    metadata: dict[str, object]


class ClaimVerificationView(BaseModel):
    id: UUID
    label: str
    confidence_score: float | None
    methodology_version: str
    confidence_factors: dict[str, object]
    reasoning_trace: dict[str, object]
    created_at: datetime


class ArticleClaimView(BaseModel):
    id: UUID
    article_id: UUID
    article_version_id: UUID
    claim_text: str
    claim_sha256: str
    sentence_index: int
    extractor_version: str
    extraction_features: dict[str, object]
    created_at: datetime
    evidence_links: list[ClaimEvidenceLinkView]
    latest_verification: ClaimVerificationView | None




class ClaimEvidenceSearchRunSummaryView(BaseModel):
    id: UUID
    status: str
    planner_version: str
    retrieval_complete: bool
    source_count: int
    evidence_count: int
    started_at: datetime
    completed_at: datetime | None
    plan: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class ClaimConflictSummaryView(BaseModel):
    id: UUID
    state: str
    confidence: float
    support_weight: float
    contradiction_weight: float
    dispute_weight: float
    temporal_update_weight: float
    independent_lineage_count: int
    primary_support: bool
    primary_contradiction: bool
    resolver_version: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ClaimReviewFlagSummaryView(BaseModel):
    id: UUID
    state: str
    severity: str
    actions: list[str] = Field(default_factory=list)
    reason: str
    resolved_at: datetime | None
    created_at: datetime


class ClaimInvestigationView(BaseModel):
    claim: ArticleClaimView
    article_title: str
    event_id: UUID
    publisher_name: str
    lineages: list[EvidenceLineageSummaryView] = Field(default_factory=list)
    latest_search_run: ClaimEvidenceSearchRunSummaryView | None = None
    latest_conflict: ClaimConflictSummaryView | None = None
    review_flags: list[ClaimReviewFlagSummaryView] = Field(default_factory=list)
    verification_history: list[ClaimVerificationView] = Field(default_factory=list)

class QualityDimensionView(BaseModel):
    name: str
    score: float | None
    status: str
    explanation: str
    sample_size: int | None = None


class ArticleQualityProfileView(BaseModel):
    article_id: UUID
    version_id: UUID | None
    methodology_version: str
    assessment_scope: str
    overall_evidence_readiness: float | None
    dimensions: list[QualityDimensionView]
    claim_count: int
    checkable_claim_count: int
    verified_claim_count: int
    independent_evidence_links: int
    evidence_domain_count: int
    unresolved_conflict_claim_count: int = 0
    temporal_evolution_claim_count: int = 0
    resolved_conflict_claim_count: int = 0
    latest_conflict_states: dict[str, int] = Field(default_factory=dict)
    review_required_claim_count: int = 0
    critical_review_claim_count: int = 0
    generated_at: datetime


class ArticleVersionChangeView(BaseModel):
    kind: str
    significance: str
    old_text: str | None
    new_text: str | None
    old_sentence_index: int | None = None
    new_sentence_index: int | None = None
    similarity: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ArticleVersionDiffView(BaseModel):
    methodology_version: str
    added_count: int
    removed_count: int
    replaced_count: int
    numeric_change_count: int
    temporal_change_count: int
    material_change_count: int
    changes: list[ArticleVersionChangeView]


class ArticleVersionHistoryEntryView(BaseModel):
    version_id: UUID
    version_number: int
    title: str
    source_url: str
    final_url: str
    published_at: datetime | None
    retrieved_at: datetime
    content_sha256: str
    extraction_method: str
    extraction_warnings: list[str]
    diff_from_previous: ArticleVersionDiffView | None


class ArticleVersionHistoryView(BaseModel):
    article_id: UUID
    canonical_url: str
    version_count: int
    entries: list[ArticleVersionHistoryEntryView]


class ClaimVerificationSnapshotView(BaseModel):
    label: str
    confidence_score: float | None
    methodology_version: str
    created_at: datetime


class ClaimHistoryRevisionView(BaseModel):
    claim_id: UUID
    article_version_id: UUID
    version_number: int
    retrieved_at: datetime
    claim_text: str
    claim_type: str | None
    quantities: list[dict[str, object]]
    temporal_references: list[dict[str, object]]
    verification_label: str | None
    verification_confidence: float | None
    verification_history: list[ClaimVerificationSnapshotView] = Field(default_factory=list)


class ClaimHistoryFamilyView(BaseModel):
    family_key: str
    family_text: str | None
    first_version_number: int
    last_version_number: int
    active_in_latest_version: bool
    changed_across_versions: bool
    revisions: list[ClaimHistoryRevisionView]


class ArticleClaimHistoryView(BaseModel):
    article_id: UUID
    latest_version_number: int | None
    families: list[ClaimHistoryFamilyView]


class EventTimelinePointView(BaseModel):
    occurred_at: datetime
    point_type: str
    article_id: UUID | None = None
    article_version_id: UUID | None = None
    version_number: int | None = None
    publisher_id: UUID | None = None
    title: str
    source_url: str | None = None
    published_at: datetime | None = None
    claim_count: int = 0
    material_change_count: int = 0
    numeric_change_count: int = 0
    temporal_change_count: int = 0
    metadata: dict[str, object] = Field(default_factory=dict)


class EventTimelineView(BaseModel):
    event_id: UUID
    timeline_basis: str
    time_semantics_note: str
    title: str
    first_detected_at: datetime
    last_material_change_at: datetime
    article_count: int
    publisher_count: int
    timeline_points: list[EventTimelinePointView]


class ClaimVerificationRecomputeCommand(BaseModel):
    retrieval_complete: bool = False


class ClaimVerificationExecutionView(BaseModel):
    claim_id: UUID
    verification: ClaimVerificationView
