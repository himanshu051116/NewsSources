from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FetchFrequency(StrEnum):
    MANUAL = "manual"
    EVERY_15_MINUTES = "every_15_minutes"
    HOURLY = "hourly"
    EVERY_6_HOURS = "every_6_hours"
    DAILY = "daily"


class DiscoverPublisherCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    publisher_name: str = Field(min_length=1, max_length=300)
    website_url: str = Field(min_length=1, max_length=2_000)
    fetch_frequency: FetchFrequency = FetchFrequency.HOURLY
    manual_endpoints: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("manual_endpoints")
    @classmethod
    def strip_manual_endpoints(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class DiscoveredChannelView(BaseModel):
    id: UUID
    endpoint_url: str
    channel_type: str
    source: str
    item_count: int
    created: bool


class PublisherSourceView(BaseModel):
    id: UUID
    name: str
    slug: str
    canonical_domain: str
    homepage_url: str | None
    fetch_frequency: FetchFrequency
    discovery_status: str
    discovery_message: str | None
    rss_feed_count: int
    sitemap_count: int
    last_fetched_at: datetime | None
    articles_discovered: int
    articles_extracted: int
    duplicates_skipped: int
    failed_articles: int
    current_status: str
    rejected_articles: int = 0
    last_article_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PublisherDiscoveryResult(BaseModel):
    publisher: PublisherSourceView
    channels: list[DiscoveredChannelView]
    attempted_endpoint_count: int
    valid_endpoint_count: int
    invalid_endpoint_count: int
    manual_fallback_available: bool


class FetchJobView(BaseModel):
    id: UUID
    publisher_id: UUID | None
    job_type: str
    status: str
    publishers_total: int
    publishers_processed: int
    urls_discovered: int
    articles_queued: int
    articles_extracted: int
    duplicates_skipped: int
    failed_articles: int
    message: str | None
    pending_articles: int = 0
    channels_remaining: int = 0
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class FetchRequestAccepted(BaseModel):
    job_id: UUID
    status: str


class ChannelSourceHealthView(BaseModel):
    channel_id: UUID
    channel_type: str
    endpoint_url: str
    poll_count: int
    successful_poll_count: int
    not_modified_count: int
    failure_count: int
    discovered_count: int
    admitted_count: int
    observation_count: int
    consecutive_failures: int
    last_polled_at: datetime | None
    last_success_at: datetime | None
    current_poll_seconds: int
    health_score: float
    availability: float
    observation_yield: float
    recency: float
    health_status: str
    health_policy_version: str


class PublisherSourceHealthView(BaseModel):
    publisher_id: UUID
    window_hours: int
    generated_at: datetime
    channel_count: int
    healthy_channel_count: int
    watch_channel_count: int
    degraded_channel_count: int
    channels: list[ChannelSourceHealthView]


class ChannelDiscoveryAuditView(BaseModel):
    channel_id: UUID
    channel_type: str
    endpoint_url: str
    observed_candidates: int
    unique_candidates: int
    overlap_candidates: int
    first_discovery_wins: int
    unique_contribution_rate: float
    first_discovery_rate: float


class PublisherDiscoveryAuditView(BaseModel):
    publisher_id: UUID
    window_hours: int
    generated_at: datetime
    total_candidates: int
    single_channel_candidates: int
    multi_channel_candidates: int
    channels: list[ChannelDiscoveryAuditView]


class SourceCandidateView(BaseModel):
    id: UUID
    candidate_url: str
    candidate_domain: str
    evidence_type: str
    evidence_count: int
    score: float
    state: str
    first_seen_at: datetime
    last_seen_at: datetime
    discovered_from_publisher_id: UUID | None


class UpdatePublisherExtractionProfileCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    enabled: bool = True
    preferred_method: str = Field(default="auto", max_length=80)
    low_value_phrases: list[str] = Field(default_factory=list, max_length=100)
    skip_attribute_tokens: list[str] = Field(default_factory=list, max_length=100)
    skip_attribute_phrases: list[str] = Field(default_factory=list, max_length=100)
    paywall_or_partial_phrases: list[str] = Field(default_factory=list, max_length=100)
    browser_render_enabled: bool = False
    browser_allowed_domains: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("preferred_method")
    @classmethod
    def validate_preferred_method(cls, value: str) -> str:
        allowed = {
            "auto",
            "json_ld_article_body",
            "hydration_json_body",
            "visible_text_blocks",
            "trafilatura_fallback",
        }
        if value not in allowed:
            raise ValueError(f"unsupported extraction method: {value}")
        return value

    @field_validator(
        "low_value_phrases",
        "skip_attribute_tokens",
        "skip_attribute_phrases",
        "paywall_or_partial_phrases",
    )
    @classmethod
    def normalize_profile_lists(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = " ".join(item.split()).strip()
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            seen.add(key)
            output.append(normalized[:200])
        return output

    @field_validator("browser_allowed_domains")
    @classmethod
    def normalize_browser_domains(cls, value: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for item in value:
            domain = item.strip().casefold().strip(".")
            if not domain or "://" in domain or "/" in domain or len(domain) > 253:
                raise ValueError("browser_allowed_domains must contain host/domain names only")
            if domain not in seen:
                seen.add(domain)
                output.append(domain)
        return output


class PublisherExtractionProfileView(BaseModel):
    publisher_id: UUID
    domain: str
    enabled: bool
    preferred_method: str
    recommended_method: str | None
    low_value_phrases: list[str]
    skip_attribute_tokens: list[str]
    skip_attribute_phrases: list[str]
    paywall_or_partial_phrases: list[str]
    browser_render_enabled: bool
    browser_allowed_domains: list[str]
    method_stats: dict[str, object]
    sample_count: int
    full_success_count: int
    partial_success_count: int
    failure_count: int
    last_quality_score: float | None
    last_observed_at: datetime | None
    updated_at: datetime
