from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EntitySearchResultView(BaseModel):
    id: UUID
    canonical_name: str
    entity_type: str
    country_code: str | None
    score: float
    matched_alias: str | None = None
    alias_count: int = 0


class EntitySearchView(BaseModel):
    query: str
    results: list[EntitySearchResultView]
    result_count: int


class EntityAliasSummaryView(BaseModel):
    id: UUID
    alias: str
    normalized_alias: str
    language: str | None
    source: str
    confidence: float


class EntityExternalIdSummaryView(BaseModel):
    namespace: str
    external_id: str
    canonical_url: str | None
    provenance_url: str | None
    confidence: float
    verified_at: datetime | None


class EntityMentionView(BaseModel):
    id: UUID
    claim_id: UUID
    claim_text: str
    article_id: UUID
    article_title: str
    article_url: str
    event_id: UUID
    event_title: str
    publisher: str
    mention_text: str
    link_basis: str
    confidence: float
    published_at: datetime | None
    created_at: datetime


class EntityProfileView(BaseModel):
    id: UUID
    entity_key: str
    canonical_name: str
    normalized_name: str
    entity_type: str
    country_code: str | None
    external_ids: dict[str, str]
    metadata: dict[str, object]
    aliases: list[EntityAliasSummaryView] = Field(default_factory=list)
    linked_external_ids: list[EntityExternalIdSummaryView] = Field(default_factory=list)
    claim_count: int = 0
    article_count: int = 0
    event_count: int = 0
    publisher_count: int = 0
    recent_mentions: list[EntityMentionView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    resolution_status: str = "active"
    merged_into_entity_id: UUID | None = None


class EntityMentionRefreshView(BaseModel):
    entity_id: UUID
    linked_mentions: int
    linked_claims: int
    scanned_aliases: int
    methodology: str = "exact_normalized_alias_v1"
    interpretation: str = (
        "Only exact normalized canonical-name or approved-alias matches are linked automatically. "
        "Fuzzy similarity is intentionally excluded from automatic identity linking."
    )

class EntityResolutionCandidateView(BaseModel):
    id: UUID
    candidate_key: str
    candidate_type: str
    normalized_value: str
    entity_ids: list[UUID] = Field(default_factory=list)
    evidence: dict[str, object] = Field(default_factory=dict)
    status: str
    resolved_action_id: UUID | None
    created_at: datetime
    resolved_at: datetime | None


class EntityConflictScanView(BaseModel):
    detected_candidates: int
    new_candidates: int
    pending_candidates: int
    interpretation: str = (
        "Candidates are deterministic identity conflicts based on shared normalized canonical names or approved aliases. "
        "They are review prompts only; no identity is merged automatically."
    )


class EntityMergeCommand(BaseModel):
    source_entity_id: UUID
    target_entity_id: UUID
    candidate_id: UUID | None = None
    rationale: str = Field(min_length=4, max_length=2_000)


class EntitySplitAliasCommand(BaseModel):
    alias_id: UUID
    canonical_name: str | None = Field(default=None, max_length=300)
    entity_type: str | None = Field(default=None, max_length=60)
    country_code: str | None = Field(default=None, max_length=8)
    candidate_id: UUID | None = None
    rationale: str = Field(min_length=4, max_length=2_000)


class EntityResolutionActionView(BaseModel):
    id: UUID
    action_type: str
    source_entity_id: UUID
    target_entity_id: UUID | None
    new_entity_id: UUID | None
    alias_id: UUID | None
    candidate_id: UUID | None
    rationale: str
    actor_user_id: UUID | None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime

class EntityResolutionRationaleCommand(BaseModel):
    rationale: str = Field(min_length=4, max_length=2_000)
