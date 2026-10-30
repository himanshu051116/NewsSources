from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchBenchmarkQueryCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    benchmark_set: str = Field(min_length=2, max_length=120)
    query_text: str = Field(min_length=2, max_length=500)
    result_type: str = Field(default="all", pattern="^(all|event|article|claim|entity)$")
    filters: dict[str, object] = Field(default_factory=dict)
    language: str | None = Field(default=None, max_length=35)
    topic_key: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2_000)
    case_key: str | None = Field(default=None, min_length=4, max_length=64)


class SearchBenchmarkQueryView(BaseModel):
    id: UUID
    benchmark_set: str
    case_key: str
    query_text: str
    result_type: str
    filters: dict[str, object]
    language: str | None
    topic_key: str | None
    notes: str | None
    judgment_count: int = 0
    relevant_judgment_count: int = 0
    created_at: datetime


class SearchRelevanceJudgmentCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    result_type: str = Field(pattern="^(event|article|claim|entity)$")
    result_id: UUID
    relevance_grade: int = Field(ge=0, le=3)
    rationale: str | None = Field(default=None, max_length=2_000)


class SearchRelevanceJudgmentView(BaseModel):
    id: UUID
    query_id: UUID
    result_type: str
    result_id: UUID
    relevance_grade: int
    rationale: str | None
    adjudicator_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SearchBenchmarkRunCommand(BaseModel):
    search_mode: str = Field(default="lexical", pattern="^(lexical|hybrid_article_rerank)$")
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5, 10], min_length=1, max_length=8)
    max_results: int = Field(default=20, ge=1, le=100)
    slice_by: list[str] = Field(default_factory=lambda: ["language", "topic_key", "result_type"], max_length=3)


class SearchBenchmarkRunView(BaseModel):
    id: UUID
    benchmark_set: str
    search_mode: str
    query_count: int
    judged_query_count: int
    metrics: dict[str, object]
    latency: dict[str, object]
    metadata: dict[str, object]
    created_at: datetime


class SearchBenchmarkComparisonView(BaseModel):
    benchmark_set: str
    available: bool
    lexical_run_id: UUID | None = None
    hybrid_run_id: UUID | None = None
    metric_deltas: dict[str, float | None] = Field(default_factory=dict)
    latency_deltas_ms: dict[str, float | None] = Field(default_factory=dict)
    lexical_judged_query_count: int | None = None
    hybrid_judged_query_count: int | None = None
    note: str


class SearchExperimentStatusView(BaseModel):
    semantic_experiment_available: bool
    production_search_mode: str = "postgres_fts_v3_multilingual"
    experiment_mode: str = "hybrid_article_rerank_v1"
    article_only: bool = True
    embedding_model: str | None = None
    qdrant_collection: str | None = None
    guardrail: str = (
        "Semantic reranking is benchmark-only and never changes production search unless a later release explicitly promotes it after measured review."
    )


class SearchTelemetryView(BaseModel):
    window_hours: int
    observation_count: int
    first_page_count: int
    cursor_page_count: int
    p50_ms: float | None
    p95_ms: float | None
    max_ms: float | None
    mean_ms: float | None
    slow_over_1500_ms: int
    mean_returned_count: float | None
    generated_at: datetime


class SearchBenchmarkBundleJudgment(BaseModel):
    result_type: str = Field(pattern="^(event|article|claim|entity)$")
    result_id: UUID
    relevance_grade: int = Field(ge=0, le=3)
    rationale: str | None = Field(default=None, max_length=2_000)


class SearchBenchmarkBundleQuery(BaseModel):
    query_text: str = Field(min_length=2, max_length=500)
    result_type: str = Field(default="all", pattern="^(all|event|article|claim|entity)$")
    filters: dict[str, object] = Field(default_factory=dict)
    language: str | None = Field(default=None, max_length=35)
    topic_key: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2_000)
    case_key: str | None = Field(default=None, min_length=4, max_length=64)
    judgments: list[SearchBenchmarkBundleJudgment] = Field(default_factory=list, max_length=2_000)


class SearchBenchmarkBundle(BaseModel):
    schema_version: str = "search-benchmark-bundle-v1"
    benchmark_set: str
    queries: list[SearchBenchmarkBundleQuery] = Field(default_factory=list)
    exported_at: datetime


class SearchBenchmarkImportCommand(BaseModel):
    benchmark_set: str = Field(min_length=2, max_length=120)
    queries: list[SearchBenchmarkBundleQuery] = Field(min_length=1, max_length=2_000)


class SearchBenchmarkImportView(BaseModel):
    benchmark_set: str
    query_count: int
    judgment_count: int
    existing_query_count: int


class SearchSlowQueryGroupView(BaseModel):
    query_fingerprint: str
    result_type: str
    filters: dict[str, object]
    observation_count: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    mean_ms: float
    cursor_page_ratio: float
    mean_result_count: float
    mean_returned_count: float
    diagnosis: list[str] = Field(default_factory=list)


class SearchSlowDiagnosticsView(BaseModel):
    window_hours: int
    threshold_ms: float
    group_count: int
    groups: list[SearchSlowQueryGroupView] = Field(default_factory=list)
    privacy_note: str = (
        "Raw query text is not stored in operational search telemetry; diagnostics use query fingerprints and filter shapes."
    )
    generated_at: datetime


class SearchSemanticCoverageView(BaseModel):
    current_article_versions: int
    indexed_article_versions: int
    fresh_article_versions: int
    missing_article_versions: int
    stale_article_versions: int
    expected_model: str | None = None
    fresh_coverage: float | None
    indexed_coverage: float | None
    generated_at: datetime
    interpretation: str = (
        "Coverage is computed over current article versions only. A fresh semantic entry must match the current content hash and, when configured, the expected embedding model."
    )


class SearchPromotionPolicyCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(default="Default search promotion policy", min_length=2, max_length=160)
    min_query_count: int = Field(default=30, ge=1, le=10_000)
    min_judgment_coverage: float = Field(default=0.90, ge=0, le=1)
    min_relevant_query_coverage: float = Field(default=0.60, ge=0, le=1)
    min_ndcg_delta: float = Field(default=0.01, ge=-1, le=1)
    min_mrr_delta: float = Field(default=0.0, ge=-1, le=1)
    min_recall_delta: float = Field(default=-0.01, ge=-1, le=1)
    max_hybrid_p95_ms: float = Field(default=1200.0, ge=1, le=120_000)
    max_p95_regression_ms: float = Field(default=350.0, ge=0, le=120_000)
    min_semantic_coverage: float = Field(default=0.95, ge=0, le=1)
    min_slice_judged_queries: int = Field(default=5, ge=1, le=10_000)
    max_slice_ndcg_drop: float = Field(default=0.03, ge=0, le=1)
    required_languages: list[str] = Field(default_factory=lambda: ["en", "hi"], max_length=20)
    required_topics: list[str] = Field(default_factory=list, max_length=50)


class SearchPromotionPolicyView(SearchPromotionPolicyCommand):
    id: UUID | None = None
    benchmark_set: str
    persisted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SearchPromotionCheckView(BaseModel):
    key: str
    state: str
    actual: object | None = None
    threshold: object | None = None
    message: str


class SearchPromotionEvaluationView(BaseModel):
    id: UUID
    policy_id: UUID
    benchmark_set: str
    lexical_run_id: UUID | None = None
    hybrid_run_id: UUID | None = None
    benchmark_fingerprint: str | None = None
    state: str
    checks: list[SearchPromotionCheckView] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    semantic_coverage: dict[str, object] = Field(default_factory=dict)
    methodology_version: str
    interpretation: str
    created_at: datetime


class SearchPromotionDecisionCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decision: str = Field(pattern="^(approve_candidate|hold|reject)$")
    rationale: str = Field(min_length=5, max_length=4_000)


class SearchPromotionDecisionView(BaseModel):
    id: UUID
    evaluation_id: UUID
    benchmark_set: str
    gate_state: str
    decision: str
    rationale: str
    decided_by_user_id: UUID | None
    created_at: datetime
    guardrail: str = "A recorded decision is governance metadata only and does not enable or deploy a production search mode."
class SearchDeploymentConfigCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    state: str = Field(default="off", pattern="^(off|shadow|canary|paused)$")
    target_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    promotion_decision_id: UUID | None = None
    max_hybrid_p95_ms: float = Field(default=1500.0, ge=1.0, le=120_000.0)
    max_hybrid_error_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    min_hybrid_samples: int = Field(default=30, ge=1, le=100_000)
    circuit_window_minutes: int = Field(default=15, ge=1, le=1_440)
    auto_pause: bool = True
    rationale: str = Field(min_length=5, max_length=4_000)


class SearchDeploymentConfigView(BaseModel):
    id: UUID | None = None
    name: str = "production"
    state: str = "off"
    target_percent: float = 0.0
    promotion_decision_id: UUID | None = None
    benchmark_set: str | None = None
    approval_active: bool = False
    max_hybrid_p95_ms: float = 1500.0
    max_hybrid_error_rate: float = 0.05
    min_hybrid_samples: int = 30
    circuit_window_minutes: int = 15
    auto_pause: bool = True
    updated_at: datetime | None = None
    guardrail: str = (
        "Production semantic exposure defaults to 0%. CANARY requires an explicit human approve_candidate decision on a PASS promotion gate."
    )


class SearchDeploymentTelemetryView(BaseModel):
    window_minutes: int
    sample_count: int
    hybrid_assigned_count: int
    hybrid_served_count: int
    shadow_assigned_count: int = 0
    shadow_error_count: int = 0
    shadow_error_rate: float | None = None
    shadow_p95_ms: float | None = None
    fallback_count: int
    hybrid_error_count: int
    hybrid_error_rate: float | None
    hybrid_p50_ms: float | None
    hybrid_p95_ms: float | None
    lexical_p50_ms: float | None
    lexical_p95_ms: float | None
    lexical_exposure_count: int = 0
    hybrid_exposure_count: int = 0
    lexical_open_exposure_count: int = 0
    hybrid_open_exposure_count: int = 0
    lexical_open_rate: float | None = None
    hybrid_open_rate: float | None = None
    open_outcome_count: int = 0
    generated_at: datetime


class SearchDeploymentActionView(BaseModel):
    id: UUID
    action: str
    previous_state: str
    new_state: str
    target_percent: float
    rationale: str
    metadata: dict[str, object] = Field(default_factory=dict)
    actor_user_id: UUID | None
    created_at: datetime


class SearchDeploymentStatusView(BaseModel):
    config: SearchDeploymentConfigView
    telemetry: SearchDeploymentTelemetryView
    circuit_breaker_state: str
    circuit_breaker_reasons: list[str] = Field(default_factory=list)
    latest_actions: list[SearchDeploymentActionView] = Field(default_factory=list)
    production_mode: str = "lexical"
    interpretation: str = (
        "Live canary control is separate from benchmark approval. A PASS gate and human approval are prerequisites, not an automatic deployment trigger."
    )


class SearchDeploymentRollbackCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    rationale: str = Field(min_length=5, max_length=4_000)


class SearchDeploymentOutcomeCommand(BaseModel):
    action: str = Field(default="open_result", pattern="^(open_result)$")
    exposure_id: UUID
    result_type: str = Field(pattern="^(event|article|claim|entity)$")
    result_id: UUID
    rank: int | None = Field(default=None, ge=1, le=1000)

