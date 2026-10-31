from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.base import Base


class PublisherModel(Base):
    __tablename__ = "publishers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(300))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    canonical_domain: Mapped[str] = mapped_column(String(253), unique=True)
    homepage_url: Mapped[str | None] = mapped_column(Text)
    fetch_frequency: Mapped[str] = mapped_column(String(40), default="hourly")
    discovery_status: Mapped[str] = mapped_column(String(40), default="pending")
    discovery_message: Mapped[str | None] = mapped_column(Text)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublisherDomainModel(Base):
    __tablename__ = "publisher_domains"
    __table_args__ = (
        UniqueConstraint("domain", name="uq_publisher_domains_domain"),
        UniqueConstraint(
            "publisher_id",
            "domain",
            name="uq_publisher_domains_publisher_domain",
        ),
        Index("ix_publisher_domains_publisher_active", "publisher_id", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    domain: Mapped[str] = mapped_column(String(253))
    homepage_url: Mapped[str | None] = mapped_column(Text)
    edition_name: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(35))
    region: Mapped[str | None] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    discovered_via: Mapped[str] = mapped_column(String(80))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublisherExtractionProfileModel(Base):
    __tablename__ = "publisher_extraction_profiles"
    __table_args__ = (
        UniqueConstraint("publisher_id", name="uq_publisher_extraction_profile_publisher"),
        Index("ix_publisher_extraction_profiles_domain", "domain"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    domain: Mapped[str] = mapped_column(String(253))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_method: Mapped[str] = mapped_column(String(80), default="auto")
    recommended_method: Mapped[str | None] = mapped_column(String(80))
    low_value_phrases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    skip_attribute_tokens: Mapped[list[str]] = mapped_column(JSONB, default=list)
    skip_attribute_phrases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    paywall_or_partial_phrases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    browser_render_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    browser_allowed_domains: Mapped[list[str]] = mapped_column(JSONB, default=list)
    method_stats: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    full_success_count: Mapped[int] = mapped_column(Integer, default=0)
    partial_success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_quality_score: Mapped[float | None] = mapped_column(Float)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RobotsSnapshotModel(Base):
    __tablename__ = "robots_snapshots"
    __table_args__ = (
        Index("ix_robots_snapshots_domain_fetched", "publisher_domain_id", "fetched_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_domain_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publisher_domains.id"),
    )
    robots_url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    body_sha256: Mapped[str | None] = mapped_column(String(64))
    body_text: Mapped[str | None] = mapped_column(Text)
    policy_state: Mapped[str] = mapped_column(String(40))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)


class SourceCandidateModel(Base):
    __tablename__ = "source_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_url", name="uq_source_candidates_url"),
        Index("ix_source_candidates_state_score", "state", "score"),
        Index("ix_source_candidates_domain", "candidate_domain"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    discovered_from_publisher_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    candidate_url: Mapped[str] = mapped_column(Text)
    candidate_domain: Mapped[str] = mapped_column(String(253))
    evidence_type: Mapped[str] = mapped_column(String(80))
    evidence_count: Mapped[int] = mapped_column(Integer, default=1)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    state: Mapped[str] = mapped_column(String(40))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)


class DiscoveryChannelModel(Base):
    __tablename__ = "discovery_channels"
    __table_args__ = (
        UniqueConstraint("publisher_id", "endpoint_url", name="publisher_endpoint"),
        Index("ix_discovery_channels_next_poll", "active", "next_poll_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    channel_type: Mapped[str] = mapped_column(String(40))
    endpoint_url: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    strategy_version: Mapped[str] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    poll_min_seconds: Mapped[int] = mapped_column(Integer, default=60)
    poll_max_seconds: Mapped[int] = mapped_column(Integer, default=3_600)
    current_poll_seconds: Mapped[int] = mapped_column(Integer, default=300)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_version: Mapped[int] = mapped_column(Integer, default=0)
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("fetch_jobs.id"))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UrlCandidateModel(Base):
    __tablename__ = "url_candidates"
    __table_args__ = (
        Index("ix_url_candidates_frontier", "state", "next_fetch_at", "priority_score"),
        Index(
            "ix_url_candidates_freshness_queue",
            "state",
            "published_at",
            "first_discovered_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    normalized_url: Mapped[str] = mapped_column(Text)
    url_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    state: Mapped[str] = mapped_column(String(40))
    processing_stage: Mapped[str] = mapped_column(String(60), default="queued")
    priority_score: Mapped[float] = mapped_column(Float)
    priority_components: Mapped[dict[str, float]] = mapped_column(JSONB)
    priority_policy_version: Mapped[str] = mapped_column(String(100))
    next_fetch_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url_type: Mapped[str | None] = mapped_column(String(60))
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_version: Mapped[int] = mapped_column(Integer, default=0)
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    originating_fetch_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("fetch_jobs.id"))
    current_worker: Mapped[str | None] = mapped_column(String(200))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    article_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    last_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_failure_code: Mapped[str | None] = mapped_column(String(160))
    last_failure_message: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(160))
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_duration_ms: Mapped[int | None] = mapped_column(Integer)
    stage_timestamps: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UrlDiscoveryModel(Base):
    __tablename__ = "url_discoveries"
    __table_args__ = (
        UniqueConstraint("url_candidate_id", "channel_id", name="candidate_channel"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    url_candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("url_candidates.id"),
    )
    channel_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discovery_channels.id"),
    )
    discovered_url: Mapped[str] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    channel_position: Mapped[int | None] = mapped_column(Integer)
    payload_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    fetch_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("fetch_jobs.id"))


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(String(240), unique=True)
    title: Mapped[str] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(40))
    assignment_status: Mapped[str] = mapped_column(String(40))
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_material_change_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleModel(Base):
    __tablename__ = "articles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    canonical_url: Mapped[str] = mapped_column(Text)
    normalized_url_hash: Mapped[bytes] = mapped_column(LargeBinary(32), unique=True)
    title: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(35))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleVersionModel(Base):
    __tablename__ = "article_versions"
    __table_args__ = (
        UniqueConstraint(
            "article_id",
            "version_number",
            name="uq_article_versions_article_number",
        ),
        # The same body can reappear after an intervening correction.
        # Uniqueness belongs to the monotonically increasing version_number.
        Index("ix_article_versions_article_content", "article_id", "content_sha256"),
        Index("ix_article_versions_article_created", "article_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    source_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    byline: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(35))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str] = mapped_column(String(64))
    text_content: Mapped[str] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(100))
    extraction_warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    semantic_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    semantic_model: Mapped[str | None] = mapped_column(String(200))
    semantic_content_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleClaimModel(Base):
    __tablename__ = "article_claims"
    __table_args__ = (
        UniqueConstraint("article_version_id", "claim_sha256", name="article_version_claim"),
        Index("ix_article_claims_article_created", "article_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    article_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("article_versions.id"),
    )
    claim_text: Mapped[str] = mapped_column(Text)
    claim_sha256: Mapped[str] = mapped_column(String(64))
    sentence_index: Mapped[int] = mapped_column(Integer)
    extractor_version: Mapped[str] = mapped_column(String(100))
    extraction_features: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClaimEvidenceLinkModel(Base):
    __tablename__ = "claim_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "evidence_article_version_id",
            "relationship",
            name="claim_evidence_relationship",
        ),
        Index("ix_claim_evidence_links_claim", "claim_id", "retrieved_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    evidence_article_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("articles.id"),
    )
    evidence_article_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("article_versions.id"),
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(80))
    relationship: Mapped[str] = mapped_column(String(80))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    similarity_score: Mapped[float | None] = mapped_column(Float)
    independence_score: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClaimVerificationModel(Base):
    __tablename__ = "claim_verifications"
    __table_args__ = (
        Index("ix_claim_verifications_claim_created", "claim_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    label: Mapped[str] = mapped_column(String(40))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    methodology_version: Mapped[str] = mapped_column(String(100))
    confidence_factors: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    reasoning_trace: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceAuthorityProfileModel(Base):
    __tablename__ = "evidence_authority_profiles"
    __table_args__ = (
        UniqueConstraint("name", "jurisdiction", "evidence_class", name="uq_evidence_authority_scope"),
        Index("ix_evidence_authority_class_active", "evidence_class", "active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(240))
    evidence_class: Mapped[str] = mapped_column(String(80))
    jurisdiction: Mapped[str] = mapped_column(String(120))
    language: Mapped[str | None] = mapped_column(String(35))
    base_url: Mapped[str] = mapped_column(Text)
    allowed_domains: Mapped[list[str]] = mapped_column(JSONB, default=list)
    search_url_template: Mapped[str | None] = mapped_column(Text)
    adapter_type: Mapped[str] = mapped_column(String(60), default="generic_html_search")
    adapter_config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    trust_scope: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceSearchRunModel(Base):
    __tablename__ = "evidence_search_runs"
    __table_args__ = (
        Index("ix_evidence_search_runs_claim_created", "claim_id", "created_at"),
        Index("ix_evidence_search_runs_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    plan_key: Mapped[str] = mapped_column(String(64))
    planner_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40))
    plan: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    retrieval_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidencePassageEvaluationModel(Base):
    __tablename__ = "evidence_passage_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "source_url",
            "passage_sha256",
            name="uq_evidence_passage_claim_source_hash",
        ),
        Index("ix_evidence_passage_eval_claim_retrieved", "claim_id", "retrieved_at"),
        Index("ix_evidence_passage_eval_run", "search_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    search_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evidence_search_runs.id"),
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(80))
    evidence_class: Mapped[str | None] = mapped_column(String(80))
    passage_text: Mapped[str] = mapped_column(Text)
    passage_sha256: Mapped[str] = mapped_column(String(64))
    stance: Mapped[str] = mapped_column(String(40))
    stance_confidence: Mapped[float] = mapped_column(Float)
    assessor_version: Mapped[str] = mapped_column(String(100))
    temporal_relation: Mapped[str] = mapped_column(String(60))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    independence_score: Mapped[float] = mapped_column(Float, default=0.0)
    primary_source: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceRetrievalAttemptModel(Base):
    __tablename__ = "evidence_retrieval_attempts"
    __table_args__ = (
        Index("ix_evidence_retrieval_attempts_run_created", "search_run_id", "created_at"),
        Index("ix_evidence_retrieval_attempts_authority_created", "authority_profile_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    search_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence_search_runs.id")
    )
    authority_profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence_authority_profiles.id")
    )
    search_url: Mapped[str | None] = mapped_column(Text)
    candidate_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(60))
    http_status: Mapped[int | None] = mapped_column(Integer)
    body_sha256: Mapped[str | None] = mapped_column(String(64))
    error_type: Mapped[str | None] = mapped_column(String(160))
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublisherReliabilitySnapshotModel(Base):
    __tablename__ = "publisher_reliability_snapshots"
    __table_args__ = (
        Index(
            "ix_publisher_reliability_scope_window",
            "publisher_id",
            "topic_key",
            "window_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publishers.id")
    )
    topic_key: Mapped[str] = mapped_column(String(80))
    methodology_version: Mapped[str] = mapped_column(String(120))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    posterior_mean: Mapped[float | None] = mapped_column(Float)
    interval_low: Mapped[float | None] = mapped_column(Float)
    interval_high: Mapped[float | None] = mapped_column(Float)
    effective_successes: Mapped[float] = mapped_column(Float, default=0.0)
    effective_failures: Mapped[float] = mapped_column(Float, default=0.0)
    effective_sample_size: Mapped[float] = mapped_column(Float, default=0.0)
    raw_observation_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_observation_count: Mapped[int] = mapped_column(Integer, default=0)
    prior_alpha: Mapped[float] = mapped_column(Float)
    prior_beta: Mapped[float] = mapped_column(Float)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemporalKnowledgeNodeModel(Base):
    __tablename__ = "temporal_knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("event_id", "node_key", name="uq_temporal_knowledge_event_node"),
        Index("ix_temporal_knowledge_nodes_event_observed", "event_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    node_key: Mapped[str] = mapped_column(String(120))
    node_type: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graph_version: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemporalKnowledgeEdgeModel(Base):
    __tablename__ = "temporal_knowledge_edges"
    __table_args__ = (
        UniqueConstraint("event_id", "edge_key", name="uq_temporal_knowledge_event_edge"),
        Index("ix_temporal_knowledge_edges_event_observed", "event_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    edge_key: Mapped[str] = mapped_column(String(64))
    source_key: Mapped[str] = mapped_column(String(120))
    target_key: Mapped[str] = mapped_column(String(120))
    relation: Mapped[str] = mapped_column(String(60))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    graph_version: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleFetchRunModel(Base):
    __tablename__ = "article_fetch_runs"
    __table_args__ = (
        Index("ix_article_fetch_runs_candidate_started", "candidate_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    candidate_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("url_candidates.id"),
    )
    worker_id: Mapped[str] = mapped_column(String(200))
    trace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    final_url: Mapped[str | None] = mapped_column(Text)
    body_sha256: Mapped[str | None] = mapped_column(String(64))
    error_type: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)
    fetch_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fetch_jobs.id")
    )
    lease_version: Mapped[int] = mapped_column(Integer, default=0)


class EventCommitmentModel(Base):
    __tablename__ = "event_commitments"
    __table_args__ = (
        UniqueConstraint("event_id", "commitment_key", name="uq_event_commitment_key"),
        Index("ix_event_commitments_event_status", "event_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    source_claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("article_claims.id"),
    )
    commitment_key: Mapped[str] = mapped_column(String(64))
    commitment_type: Mapped[str] = mapped_column(String(40))
    commitment_text: Mapped[str] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(Text)
    deadline_text: Mapped[str | None] = mapped_column(Text)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40))
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommitmentOutcomeModel(Base):
    __tablename__ = "commitment_outcomes"
    __table_args__ = (
        Index("ix_commitment_outcomes_commitment_observed", "commitment_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    commitment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("event_commitments.id"),
    )
    source_claim_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("article_claims.id"),
    )
    evidence_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    tracker_version: Mapped[str] = mapped_column(String(100))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reasoning: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventAssignmentModel(Base):
    __tablename__ = "event_assignments"
    __table_args__ = (
        Index("ix_event_assignments_article_current", "article_id", "is_current"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    state: Mapped[str] = mapped_column(String(40))
    score: Mapped[float | None] = mapped_column(Float)
    candidate_features: Mapped[dict[str, float]] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(String(100))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_unpublished", "published_at", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_type: Mapped[str] = mapped_column(String(200))
    event_version: Mapped[int] = mapped_column(Integer, default=1)
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    producer: Mapped[str] = mapped_column(String(200))
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    causation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    traceparent: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsumerInboxModel(Base):
    __tablename__ = "consumer_inbox"
    __table_args__ = (
        UniqueConstraint("consumer_name", "event_id", name="consumer_event"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    consumer_name: Mapped[str] = mapped_column(String(200))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(200))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handler_version: Mapped[str] = mapped_column(String(100))


class ChannelPollRunModel(Base):
    __tablename__ = "channel_poll_runs"
    __table_args__ = (
        Index("ix_channel_poll_runs_channel_started", "channel_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    channel_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discovery_channels.id"),
    )
    worker_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)
    not_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    admitted_count: Mapped[int] = mapped_column(Integer, default=0)
    observation_count: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    fetch_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("fetch_jobs.id"))
    lease_version: Mapped[int] = mapped_column(Integer, default=0)


class FetchJobModel(Base):
    __tablename__ = "fetch_jobs"
    __table_args__ = (
        Index("ix_fetch_jobs_status_created", "status", "created_at"),
        Index("ix_fetch_jobs_publisher_created", "publisher_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publishers.id"),
    )
    job_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    publishers_total: Mapped[int] = mapped_column(Integer, default=0)
    publishers_processed: Mapped[int] = mapped_column(Integer, default=0)
    urls_discovered: Mapped[int] = mapped_column(Integer, default=0)
    articles_queued: Mapped[int] = mapped_column(Integer, default=0)
    articles_extracted: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0)
    failed_articles: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FetchJobObservationModel(Base):
    __tablename__ = "fetch_job_observations"
    __table_args__ = (
        UniqueConstraint("fetch_job_id", "candidate_id", "channel_id", name="uq_fetch_job_observation"),
        Index("ix_fetch_job_observations_job_created", "fetch_job_id", "candidate_created", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    fetch_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("fetch_jobs.id"))
    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("url_candidates.id"))
    channel_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("discovery_channels.id"))
    candidate_created: Mapped[bool] = mapped_column(Boolean, default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleIdentityModel(Base):
    __tablename__ = "article_identities"
    __table_args__ = (
        UniqueConstraint("identity_key", name="uq_article_identities_key"),
        Index("ix_article_identities_last_observed", "last_observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    identity_key: Mapped[str] = mapped_column(String(64))
    representative_article_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    member_count: Mapped[int] = mapped_column(Integer, default=1)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleIdentityMemberModel(Base):
    __tablename__ = "article_identity_members"
    __table_args__ = (
        UniqueConstraint("article_id", name="uq_article_identity_member_article"),
        Index("ix_article_identity_members_identity", "identity_id", "created_at"),
        Index("ix_article_identity_members_content", "content_sha256"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    identity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_identities.id"))
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    publisher_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("publishers.id"))
    membership_basis: Mapped[str] = mapped_column(String(40))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    similarity: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlatformUserModel(Base):
    __tablename__ = "platform_users"
    __table_args__ = (
        UniqueConstraint(
            "auth_provider",
            "auth_provider_user_id",
            name="uq_platform_users_provider_subject",
        ),
        Index("ix_platform_users_access_status", "access_status", "requested_at"),
        Index("ix_platform_users_email", "verified_email"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    auth_provider: Mapped[str] = mapped_column(String(80))
    auth_provider_user_id: Mapped[str] = mapped_column(String(255))
    verified_email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(300))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    access_status: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(40))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessRequestModel(Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        Index("ix_access_requests_status_requested", "status", "requested_at"),
        Index("ix_access_requests_user", "user_id", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    status: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str | None] = mapped_column(String(500))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_admin_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessAuditLogModel(Base):
    __tablename__ = "access_audit_log"
    __table_args__ = (
        Index("ix_access_audit_affected_created", "affected_user_id", "created_at"),
        Index("ix_access_audit_actor_created", "actor_user_id", "created_at"),
        Index("ix_access_audit_action_created", "action", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    action: Mapped[str] = mapped_column(String(80))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    affected_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_users.id"),
    )
    previous_status: Mapped[str | None] = mapped_column(String(40))
    new_status: Mapped[str | None] = mapped_column(String(40))
    previous_role: Mapped[str | None] = mapped_column(String(40))
    new_role: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MediaOwnershipGroupModel(Base):
    __tablename__ = "media_ownership_groups"
    __table_args__ = (
        UniqueConstraint("name", name="uq_media_ownership_groups_name"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(300))
    canonical_domain: Mapped[str | None] = mapped_column(String(253))
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PublisherOwnershipMembershipModel(Base):
    __tablename__ = "publisher_ownership_memberships"
    __table_args__ = (
        Index("ix_publisher_ownership_publisher_valid", "publisher_id", "valid_from", "valid_to"),
        Index("ix_publisher_ownership_group_valid", "group_id", "valid_from", "valid_to"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    publisher_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("publishers.id"))
    group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("media_ownership_groups.id"))
    relationship: Mapped[str] = mapped_column(String(60))
    ownership_fraction: Mapped[float | None] = mapped_column(Float)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provenance_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CanonicalEntityModel(Base):
    __tablename__ = "canonical_entities"
    __table_args__ = (
        UniqueConstraint("entity_key", name="uq_canonical_entities_key"),
        Index("ix_canonical_entities_normalized_type", "normalized_name", "entity_type"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    entity_key: Mapped[str] = mapped_column(String(64))
    canonical_name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(60))
    country_code: Mapped[str | None] = mapped_column(String(8))
    external_ids: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolution_status: Mapped[str] = mapped_column(String(24), default="active")
    merged_into_entity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"), nullable=True
    )


class EntityAliasModel(Base):
    __tablename__ = "entity_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "normalized_alias", name="uq_entity_alias_normalized"),
        Index("ix_entity_alias_lookup", "normalized_alias"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    alias: Mapped[str] = mapped_column(Text)
    normalized_alias: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(35))
    source: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntityMentionModel(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        UniqueConstraint("entity_id", "claim_id", "normalized_mention", name="uq_entity_mention_claim_text"),
        Index("ix_entity_mentions_entity_created", "entity_id", "created_at"),
        Index("ix_entity_mentions_claim", "claim_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    article_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_versions.id"))
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    mention_text: Mapped[str] = mapped_column(Text)
    normalized_mention: Mapped[str] = mapped_column(Text)
    link_basis: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntityResolutionCandidateModel(Base):
    __tablename__ = "entity_resolution_candidates"
    __table_args__ = (
        UniqueConstraint("candidate_key", name="uq_entity_resolution_candidate_key"),
        Index("ix_entity_resolution_candidates_status_created", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    candidate_key: Mapped[str] = mapped_column(String(64))
    candidate_type: Mapped[str] = mapped_column(String(40))
    normalized_value: Mapped[str] = mapped_column(Text)
    entity_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    resolved_action_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("entity_resolution_actions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EntityResolutionActionModel(Base):
    __tablename__ = "entity_resolution_actions"
    __table_args__ = (Index("ix_entity_resolution_actions_created", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    action_type: Mapped[str] = mapped_column(String(40))
    source_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    target_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    new_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    alias_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    candidate_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("entity_resolution_candidates.id"))
    rationale: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchBenchmarkQueryModel(Base):
    __tablename__ = "search_benchmark_queries"
    __table_args__ = (
        UniqueConstraint("benchmark_set", "case_key", name="uq_search_benchmark_set_case"),
        Index("ix_search_benchmark_queries_set_created", "benchmark_set", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    case_key: Mapped[str] = mapped_column(String(64))
    query_text: Mapped[str] = mapped_column(Text)
    result_type: Mapped[str] = mapped_column(String(20), default="all")
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    language: Mapped[str | None] = mapped_column(String(35))
    topic_key: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchRelevanceJudgmentModel(Base):
    __tablename__ = "search_relevance_judgments"
    __table_args__ = (
        UniqueConstraint("query_id", "result_type", "result_id", name="uq_search_judgment_query_result"),
        Index("ix_search_relevance_query_grade", "query_id", "relevance_grade"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    query_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_benchmark_queries.id"))
    result_type: Mapped[str] = mapped_column(String(20))
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    relevance_grade: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str | None] = mapped_column(Text)
    adjudicator_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchBenchmarkRunModel(Base):
    __tablename__ = "search_benchmark_runs"
    __table_args__ = (Index("ix_search_benchmark_runs_set_created", "benchmark_set", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    search_mode: Mapped[str] = mapped_column(String(80))
    query_count: Mapped[int] = mapped_column(Integer)
    judged_query_count: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    latency: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchPromotionPolicyModel(Base):
    __tablename__ = "search_promotion_policies"
    __table_args__ = (
        UniqueConstraint("benchmark_set", name="uq_search_promotion_policy_benchmark_set"),
        Index("ix_search_promotion_policies_updated", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(160), default="Default search promotion policy")
    thresholds: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    required_languages: Mapped[list[str]] = mapped_column(JSONB, default=list)
    required_topics: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchPromotionEvaluationModel(Base):
    __tablename__ = "search_promotion_evaluations"
    __table_args__ = (
        Index("ix_search_promotion_evaluations_set_created", "benchmark_set", "created_at"),
        Index("ix_search_promotion_evaluations_policy_created", "policy_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    policy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_promotion_policies.id"))
    benchmark_set: Mapped[str] = mapped_column(String(120))
    lexical_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_benchmark_runs.id"))
    hybrid_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_benchmark_runs.id"))
    benchmark_fingerprint: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24))
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    failures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    semantic_coverage: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    methodology_version: Mapped[str] = mapped_column(String(100))
    interpretation: Mapped[str] = mapped_column(Text)
    evaluated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchPromotionDecisionModel(Base):
    __tablename__ = "search_promotion_decisions"
    __table_args__ = (Index("ix_search_promotion_decisions_evaluation_created", "evaluation_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    evaluation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_promotion_evaluations.id"))
    decision: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchDeploymentModel(Base):
    __tablename__ = "search_deployments"
    __table_args__ = (
        UniqueConstraint("name", name="uq_search_deployments_name"),
        Index("ix_search_deployments_state_updated", "state", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(80), default="production")
    state: Mapped[str] = mapped_column(String(24), default="off")
    target_percent: Mapped[float] = mapped_column(Float, default=0.0)
    promotion_decision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("search_promotion_decisions.id")
    )
    benchmark_set: Mapped[str | None] = mapped_column(String(120))
    rollout_salt: Mapped[str] = mapped_column(String(80))
    max_hybrid_p95_ms: Mapped[float] = mapped_column(Float, default=1500.0)
    max_hybrid_error_rate: Mapped[float] = mapped_column(Float, default=0.05)
    min_hybrid_samples: Mapped[int] = mapped_column(Integer, default=30)
    circuit_window_minutes: Mapped[int] = mapped_column(Integer, default=15)
    auto_pause: Mapped[bool] = mapped_column(Boolean, default=True)
    configured_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchDeploymentObservationModel(Base):
    __tablename__ = "search_deployment_observations"
    __table_args__ = (
        Index("ix_search_deployment_obs_deployment_created", "deployment_id", "created_at"),
        Index("ix_search_deployment_obs_variant_created", "served_variant", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    deployment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_deployments.id"))
    user_bucket: Mapped[int] = mapped_column(Integer)
    assigned_variant: Mapped[str] = mapped_column(String(24))
    served_variant: Mapped[str] = mapped_column(String(24))
    query_fingerprint: Mapped[str] = mapped_column(String(64))
    subject_fingerprint: Mapped[str] = mapped_column(String(64))
    result_type: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[float] = mapped_column(Float)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchDeploymentOutcomeModel(Base):
    __tablename__ = "search_deployment_outcomes"
    __table_args__ = (
        UniqueConstraint("observation_id", "action", "result_type", "result_id", name="uq_search_deployment_outcome"),
        Index("ix_search_deployment_outcomes_observation_created", "observation_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    observation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("search_deployment_observations.id")
    )
    action: Mapped[str] = mapped_column(String(32))
    result_type: Mapped[str] = mapped_column(String(20))
    result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    rank: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchDeploymentActionModel(Base):
    __tablename__ = "search_deployment_actions"
    __table_args__ = (Index("ix_search_deployment_actions_deployment_created", "deployment_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    deployment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("search_deployments.id"))
    action: Mapped[str] = mapped_column(String(32))
    previous_state: Mapped[str] = mapped_column(String(24))
    new_state: Mapped[str] = mapped_column(String(24))
    target_percent: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SearchQueryObservationModel(Base):
    __tablename__ = "search_query_observations"
    __table_args__ = (
        Index("ix_search_query_observations_created", "created_at"),
        Index("ix_search_query_observations_fingerprint_created", "query_fingerprint", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    query_fingerprint: Mapped[str] = mapped_column(String(64))
    result_type: Mapped[str] = mapped_column(String(20))
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    include_claims: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[float] = mapped_column(Float)
    result_count: Mapped[int] = mapped_column(Integer)
    returned_count: Mapped[int] = mapped_column(Integer)
    cursor_page: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationBenchmarkCaseModel(Base):
    __tablename__ = "verification_benchmark_cases"
    __table_args__ = (
        Index("ix_verification_benchmark_set_created", "benchmark_set", "created_at"),
        Index("ix_verification_benchmark_claim", "claim_id"),
        Index("ix_verification_benchmark_set_split", "benchmark_set", "split"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    benchmark_set: Mapped[str] = mapped_column(String(120))
    case_key: Mapped[str | None] = mapped_column(String(160))
    group_key: Mapped[str | None] = mapped_column(String(180))
    source_document_key: Mapped[str | None] = mapped_column(String(180))
    split: Mapped[str] = mapped_column(String(40), default="unspecified")
    topic_key: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str | None] = mapped_column(String(35))
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    predicted_label: Mapped[str] = mapped_column(String(40))
    predicted_confidence: Mapped[float] = mapped_column(Float)
    adjudicated_label: Mapped[str] = mapped_column(String(40))
    adjudication_source: Mapped[str] = mapped_column(String(200))
    adjudicator_count: Mapped[int] = mapped_column(Integer, default=1)
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationBenchmarkCandidateModel(Base):
    __tablename__ = "verification_benchmark_candidates"
    __table_args__ = (
        UniqueConstraint("benchmark_set", "case_key", name="uq_verification_benchmark_candidate_case"),
        Index("ix_verification_candidate_set_status", "benchmark_set", "status"),
        Index("ix_verification_candidate_claim", "claim_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    case_key: Mapped[str] = mapped_column(String(160))
    claim_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    group_key: Mapped[str | None] = mapped_column(String(180))
    source_document_key: Mapped[str | None] = mapped_column(String(180))
    split: Mapped[str] = mapped_column(String(40), default="test")
    topic_key: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str | None] = mapped_column(String(35))
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    predicted_label: Mapped[str] = mapped_column(String(40))
    predicted_confidence: Mapped[float] = mapped_column(Float)
    prediction_methodology: Mapped[str] = mapped_column(String(120))
    source_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="sampled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationBenchmarkAdjudicationModel(Base):
    __tablename__ = "verification_benchmark_adjudications"
    __table_args__ = (
        UniqueConstraint("candidate_id", "reviewer_key_hash", name="uq_verification_adjudication_reviewer"),
        Index("ix_verification_adjudication_set_case", "benchmark_set", "case_key"),
        Index("ix_verification_adjudication_candidate", "candidate_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("verification_benchmark_candidates.id"))
    benchmark_set: Mapped[str] = mapped_column(String(120))
    case_key: Mapped[str] = mapped_column(String(160))
    reviewer_key_hash: Mapped[str] = mapped_column(String(64))
    reviewer_role: Mapped[str] = mapped_column(String(30), default="reviewer")
    adjudicated_label: Mapped[str] = mapped_column(String(40))
    adjudication_source: Mapped[str] = mapped_column(String(300))
    adjudication_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationBenchmarkAgreementSnapshotModel(Base):
    __tablename__ = "verification_benchmark_agreement_snapshots"
    __table_args__ = (Index("ix_verification_agreement_set_created", "benchmark_set", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    methodology_version: Mapped[str] = mapped_column(String(120))
    case_count: Mapped[int] = mapped_column(Integer)
    review_count: Mapped[int] = mapped_column(Integer)
    multi_review_case_count: Mapped[int] = mapped_column(Integer)
    unanimous_case_count: Mapped[int] = mapped_column(Integer)
    disagreement_case_count: Mapped[int] = mapped_column(Integer)
    pairwise_agreement: Mapped[float | None] = mapped_column(Float)
    krippendorff_alpha_nominal: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationBenchmarkDiagnosticRunModel(Base):
    __tablename__ = "verification_benchmark_diagnostic_runs"
    __table_args__ = (Index("ix_verification_diagnostic_set_created", "benchmark_set", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    methodology_version: Mapped[str] = mapped_column(String(120))
    case_count: Mapped[int] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer)
    error_rate: Mapped[float] = mapped_column(Float)
    taxonomy_counts: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    slice_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationCalibrationSnapshotModel(Base):
    __tablename__ = "verification_calibration_snapshots"
    __table_args__ = (
        Index("ix_verification_calibration_set_created", "benchmark_set", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    methodology_version: Mapped[str] = mapped_column(String(120))
    observation_count: Mapped[int] = mapped_column(Integer)
    effective_weight: Mapped[float] = mapped_column(Float)
    brier_score: Mapped[float | None] = mapped_column(Float)
    expected_calibration_error: Mapped[float | None] = mapped_column(Float)
    mean_confidence: Mapped[float | None] = mapped_column(Float)
    empirical_accuracy: Mapped[float | None] = mapped_column(Float)
    bins: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceOrchestrationRunModel(Base):
    __tablename__ = "evidence_orchestration_runs"
    __table_args__ = (
        Index("ix_evidence_orchestration_claim_created", "claim_id", "created_at"),
        Index("ix_evidence_orchestration_search_run", "search_run_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    search_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence_search_runs.id")
    )
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    orchestration_version: Mapped[str] = mapped_column(String(120))
    required_evidence_classes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    selected_authority_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    uncovered_evidence_classes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    coverage_ratio: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClaimConflictResolutionModel(Base):
    __tablename__ = "claim_conflict_resolutions"
    __table_args__ = (
        Index("ix_claim_conflict_resolutions_claim_created", "claim_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    resolver_version: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(60))
    confidence: Mapped[float] = mapped_column(Float)
    support_weight: Mapped[float] = mapped_column(Float)
    contradiction_weight: Mapped[float] = mapped_column(Float)
    dispute_weight: Mapped[float] = mapped_column(Float)
    temporal_update_weight: Mapped[float] = mapped_column(Float)
    independent_lineage_count: Mapped[int] = mapped_column(Integer)
    primary_support: Mapped[bool] = mapped_column(Boolean, default=False)
    primary_contradiction: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationBenchmarkEvaluationModel(Base):
    __tablename__ = "verification_benchmark_evaluations"
    __table_args__ = (
        Index("ix_verification_benchmark_eval_set_created", "benchmark_set", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    methodology_version: Mapped[str] = mapped_column(String(120))
    observation_count: Mapped[int] = mapped_column(Integer)
    effective_weight: Mapped[float] = mapped_column(Float)
    accuracy: Mapped[float | None] = mapped_column(Float)
    macro_precision: Mapped[float | None] = mapped_column(Float)
    macro_recall: Mapped[float | None] = mapped_column(Float)
    macro_f1: Mapped[float | None] = mapped_column(Float)
    high_confidence_error_rate: Mapped[float | None] = mapped_column(Float)
    per_label: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    confusion_matrix: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    selective_metrics: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntityExternalIdentifierModel(Base):
    __tablename__ = "entity_external_identifiers"
    __table_args__ = (
        UniqueConstraint("namespace", "external_id", name="uq_entity_external_namespace_id"),
        UniqueConstraint(
            "entity_id", "namespace", "external_id", name="uq_entity_external_entity_namespace_id"
        ),
        Index("ix_entity_external_entity", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    namespace: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(300))
    canonical_url: Mapped[str | None] = mapped_column(Text)
    provenance_url: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OwnershipProvenanceRecordModel(Base):
    __tablename__ = "ownership_provenance_records"
    __table_args__ = (
        Index("ix_ownership_provenance_membership_observed", "membership_id", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    membership_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publisher_ownership_memberships.id")
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(80))
    passage_text: Mapped[str | None] = mapped_column(Text)
    passage_sha256: Mapped[str | None] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceSearchStoppingAssessmentModel(Base):
    __tablename__ = "evidence_search_stopping_assessments"
    __table_args__ = (
        Index("ix_search_stopping_claim_created", "claim_id", "created_at"),
        Index("ix_search_stopping_run_created", "search_run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    search_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence_search_runs.id"))
    methodology_version: Mapped[str] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(60))
    completeness_score: Mapped[float] = mapped_column(Float)
    covered_evidence_classes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    uncovered_evidence_classes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    independent_lineages: Mapped[int] = mapped_column(Integer)
    primary_records: Mapped[int] = mapped_column(Integer)
    rounds_completed: Mapped[int] = mapped_column(Integer)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleCorrectionEventModel(Base):
    __tablename__ = "article_correction_events"
    __table_args__ = (
        Index("ix_article_correction_article_created", "article_id", "created_at"),
        Index("ix_article_correction_event_created", "event_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    article_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_versions.id"))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    correction_kind: Mapped[str] = mapped_column(String(60))
    source_url: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    affected_claim_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    propagation_plan: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClaimReviewFlagModel(Base):
    __tablename__ = "claim_review_flags"
    __table_args__ = (
        Index("ix_claim_review_claim_state", "claim_id", "state"),
        Index("ix_claim_review_correction", "correction_event_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    correction_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_correction_events.id"))
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    state: Mapped[str] = mapped_column(String(40), default="review_required")
    severity: Mapped[str] = mapped_column(String(30))
    actions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reason: Mapped[str] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationQualityGateRunModel(Base):
    __tablename__ = "verification_quality_gate_runs"
    __table_args__ = (
        Index("ix_quality_gate_set_created", "benchmark_set", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    evaluation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("verification_benchmark_evaluations.id"))
    methodology_version: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(30))
    failures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    thresholds: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntityRegistryProfileModel(Base):
    __tablename__ = "entity_registry_profiles"
    __table_args__ = (
        UniqueConstraint("namespace", "name", name="uq_entity_registry_namespace_name"),
        Index("ix_entity_registry_active_namespace", "active", "namespace"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200))
    namespace: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(Text)
    search_url_template: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str | None] = mapped_column(String(35))
    adapter_type: Mapped[str] = mapped_column(String(80), default="configured_json")
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EntityRegistryLinkRunModel(Base):
    __tablename__ = "entity_registry_link_runs"
    __table_args__ = (
        Index("ix_entity_registry_link_entity_created", "entity_id", "created_at"),
        Index("ix_entity_registry_link_profile_created", "registry_profile_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("canonical_entities.id"))
    registry_profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("entity_registry_profiles.id"))
    methodology_version: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(40))
    selected_external_id: Mapped[str | None] = mapped_column(String(300))
    selected_score: Mapped[float | None] = mapped_column(Float)
    candidates: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    search_url: Mapped[str | None] = mapped_column(Text)
    response_sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OwnershipIngestRunModel(Base):
    __tablename__ = "ownership_ingest_runs"
    __table_args__ = (Index("ix_ownership_ingest_source_created", "source_name", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_count: Mapped[int] = mapped_column(Integer)
    membership_created_count: Mapped[int] = mapped_column(Integer)
    provenance_created_count: Mapped[int] = mapped_column(Integer)
    rejected_count: Mapped[int] = mapped_column(Integer)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CorrectionDependencyPropagationRunModel(Base):
    __tablename__ = "correction_dependency_propagation_runs"
    __table_args__ = (
        Index("ix_correction_dependency_event_created", "correction_event_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    correction_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("article_correction_events.id")
    )
    root_article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    methodology_version: Mapped[str] = mapped_column(String(120))
    correction_kind: Mapped[str] = mapped_column(String(60))
    max_depth: Mapped[int] = mapped_column(Integer)
    direct_dependency_count: Mapped[int] = mapped_column(Integer)
    indirect_dependency_count: Mapped[int] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    impacts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VerificationRunManifestModel(Base):
    __tablename__ = "verification_run_manifests"
    __table_args__ = (
        UniqueConstraint(
            "verification_id",
            "manifest_version",
            name="uq_verification_manifest_version",
        ),
        UniqueConstraint("manifest_sha256", name="uq_verification_manifest_sha256"),
        Index("ix_verification_manifest_claim_created", "claim_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_claims.id"))
    verification_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("claim_verifications.id")
    )
    manifest_version: Mapped[str] = mapped_column(String(120))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    code_version: Mapped[str] = mapped_column(String(40))
    claim_sha256: Mapped[str] = mapped_column(String(64))
    article_content_sha256: Mapped[str] = mapped_column(String(64))
    evidence_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    authority_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    decision_context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProductionReadinessRunModel(Base):
    __tablename__ = "production_readiness_runs"
    __table_args__ = (
        Index("ix_production_readiness_benchmark_created", "benchmark_set", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    benchmark_set: Mapped[str] = mapped_column(String(120))
    methodology_version: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(30))
    failures: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    checks: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    thresholds: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DerivedArtifactDependencyModel(Base):
    __tablename__ = "derived_artifact_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "artifact_kind",
            "artifact_id",
            "source_kind",
            "source_id",
            name="uq_derived_artifact_dependency",
        ),
        Index("ix_derived_dependency_source", "source_kind", "source_id"),
        Index("ix_derived_dependency_artifact", "artifact_kind", "artifact_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    artifact_kind: Mapped[str] = mapped_column(String(80))
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_kind: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DerivedArtifactStateModel(Base):
    __tablename__ = "derived_artifact_states"
    __table_args__ = (
        UniqueConstraint("artifact_kind", "artifact_id", name="uq_derived_artifact_state"),
        Index("ix_derived_artifact_stale", "stale", "stale_since"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    artifact_kind: Mapped[str] = mapped_column(String(80))
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    stale_reason: Mapped[str | None] = mapped_column(String(240))
    stale_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int] = mapped_column(Integer, default=0)
    last_recomputed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DerivedRecomputeJobModel(Base):
    __tablename__ = "derived_recompute_jobs"
    __table_args__ = (
        UniqueConstraint(
            "artifact_kind",
            "artifact_id",
            "generation",
            name="uq_derived_recompute_generation",
        ),
        Index("ix_derived_recompute_due", "state", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    artifact_kind: Mapped[str] = mapped_column(String(80))
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    generation: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    reason: Mapped[str] = mapped_column(String(240))
    source_kind: Mapped[str | None] = mapped_column(String(80))
    source_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(240))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))



class InvestigationModel(Base):
    __tablename__ = "investigations"
    __table_args__ = (
        Index("ix_investigations_owner_status_updated", "owner_user_id", "status", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationMemberModel(Base):
    __tablename__ = "investigation_members"
    __table_args__ = (
        UniqueConstraint("investigation_id", "user_id", name="uq_investigation_member_user"),
        Index("ix_investigation_members_user_updated", "user_id", "updated_at"),
        Index("ix_investigation_members_investigation_role", "investigation_id", "access_role"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    investigation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("investigations.id"))
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    access_role: Mapped[str] = mapped_column(String(20))
    added_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationActivityModel(Base):
    __tablename__ = "investigation_activity"
    __table_args__ = (
        Index("ix_investigation_activity_investigation_created", "investigation_id", "created_at"),
        Index("ix_investigation_activity_actor_created", "actor_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    investigation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("investigations.id"))
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InvestigationItemModel(Base):
    __tablename__ = "investigation_items"
    __table_args__ = (
        UniqueConstraint("investigation_id", "item_type", "item_id", name="uq_investigation_item_target"),
        Index("ix_investigation_items_investigation_created", "investigation_id", "created_at"),
        Index("ix_investigation_items_target", "item_type", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    investigation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("investigations.id"))
    item_type: Mapped[str] = mapped_column(String(40))
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    label_snapshot: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    added_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalystNoteModel(Base):
    __tablename__ = "analyst_notes"
    __table_args__ = (
        Index("ix_analyst_notes_investigation_created", "investigation_id", "created_at"),
        Index("ix_analyst_notes_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    investigation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("investigations.id"))
    author_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    target_type: Mapped[str] = mapped_column(String(40), default="investigation")
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SavedSearchModel(Base):
    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_saved_search_owner_name"),
        Index("ix_saved_searches_owner_updated", "owner_user_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    investigation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("investigations.id"))
    name: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(String(500))
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistModel(Base):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_watchlist_owner_name"),
        Index("ix_watchlists_owner_updated", "owner_user_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WatchlistItemModel(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "item_type", "item_id", name="uq_watchlist_item_target"),
        Index("ix_watchlist_items_watchlist_created", "watchlist_id", "created_at"),
        Index("ix_watchlist_items_target", "item_type", "item_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    watchlist_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("watchlists.id"))
    item_type: Mapped[str] = mapped_column(String(40))
    item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    label_snapshot: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    added_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceAlertAcknowledgementModel(Base):
    __tablename__ = "workspace_alert_acknowledgements"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_key", name="uq_workspace_alert_ack_user_key"),
        Index("ix_workspace_alert_ack_user_created", "user_id", "acknowledged_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    alert_key: Mapped[str] = mapped_column(String(300))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceMonitorModel(Base):
    __tablename__ = "workspace_monitors"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "target_type", "target_id", name="uq_workspace_monitor_owner_target"),
        Index("ix_workspace_monitors_due", "enabled", "next_run_at"),
        Index("ix_workspace_monitors_owner_updated", "owner_user_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cadence_minutes: Mapped[int] = mapped_column(Integer, default=360)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(240))
    lease_version: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceMonitorRunModel(Base):
    __tablename__ = "workspace_monitor_runs"
    __table_args__ = (Index("ix_workspace_monitor_runs_monitor_started", "monitor_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    monitor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workspace_monitors.id", ondelete="CASCADE"))
    lease_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_fingerprint: Mapped[str | None] = mapped_column(String(64))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    new_result_count: Mapped[int] = mapped_column(Integer, default=0)
    result_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    new_result_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceGeneratedAlertModel(Base):
    __tablename__ = "workspace_generated_alerts"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "alert_key", name="uq_workspace_generated_alert_owner_key"),
        Index("ix_workspace_generated_alerts_owner_occurred", "owner_user_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("platform_users.id"))
    alert_key: Mapped[str] = mapped_column(String(300))
    alert_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    detail: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    link: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))




class EventBriefingJobModel(Base):
    __tablename__ = "event_briefing_jobs"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_event_briefing_job_event"),
        Index("ix_event_briefing_jobs_due", "state", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    trigger_article_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_versions.id"))
    state: Mapped[str] = mapped_column(String(30), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(240))
    lease_version: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventBriefingModel(Base):
    __tablename__ = "event_briefings"
    __table_args__ = (
        UniqueConstraint("event_id", "evidence_pack_sha256", name="uq_event_briefing_evidence_pack"),
        Index("ix_event_briefings_event_generated", "event_id", "generated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    trigger_article_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_versions.id"))
    methodology_version: Mapped[str] = mapped_column(String(120))
    evidence_pack_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleHistoricalEnrichmentJobModel(Base):
    __tablename__ = "article_historical_enrichment_jobs"
    __table_args__ = (
        UniqueConstraint("article_version_id", name="uq_historical_enrichment_job_version"),
        Index("ix_historical_enrichment_jobs_due", "state", "next_attempt_at"),
        Index("ix_historical_enrichment_jobs_article_created", "article_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    article_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_versions.id"))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    state: Mapped[str] = mapped_column(String(30), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    refresh_count: Mapped[int] = mapped_column(Integer, default=0)
    last_refresh_reason: Mapped[str | None] = mapped_column(String(120))
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(240))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    query_terms: Mapped[list[str]] = mapped_column(JSONB, default=list)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ArticleHistoricalContextModel(Base):
    __tablename__ = "article_historical_contexts"
    __table_args__ = (
        UniqueConstraint("article_version_id", name="uq_article_historical_context_version"),
        Index("ix_article_historical_context_article_generated", "article_id", "generated_at"),
        Index("ix_article_historical_context_event_generated", "event_id", "generated_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    article_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("articles.id"))
    article_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_versions.id"))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("events.id"))
    methodology_version: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    queries: Mapped[list[str]] = mapped_column(JSONB, default=list)
    same_event_history: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    prior_claim_history: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    internal_matches: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    external_matches: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    provider_statuses: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    timeline_summary: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    context_summary: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
