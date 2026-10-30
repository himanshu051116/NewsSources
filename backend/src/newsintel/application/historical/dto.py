from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class HistoricalProviderName(StrEnum):
    GDELT = "gdelt"
    GUARDIAN = "guardian"
    NEW_YORK_TIMES = "new_york_times"
    NEWS_API = "news_api"
    GOOGLE_FACT_CHECK = "google_fact_check"


class HistoricalSearchCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=500)
    from_date: date | None = None
    to_date: date | None = None
    language: str | None = Field(default=None, min_length=2, max_length=35)
    providers: list[HistoricalProviderName] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_dates(self) -> HistoricalSearchCommand:
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date cannot be after to_date")
        return self


class HistoricalResultType(StrEnum):
    NEWS_ARTICLE = "news_article"
    FACT_CHECK = "fact_check"


class HistoricalArticleView(BaseModel):
    provider: HistoricalProviderName
    result_type: HistoricalResultType = HistoricalResultType.NEWS_ARTICLE
    title: str
    url: str
    published_at: datetime | None = None
    source_name: str | None = None
    snippet: str | None = None
    language: str | None = None
    image_url: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class HistoricalProviderStatus(BaseModel):
    provider: HistoricalProviderName
    configured: bool
    success: bool
    result_count: int = 0
    error_code: str | None = None
    message: str | None = None


class HistoricalTimelineSummary(BaseModel):
    result_count: int
    earliest_published_at: datetime | None = None
    latest_published_at: datetime | None = None
    result_counts_by_year: dict[str, int] = Field(default_factory=dict)
    source_count: int = 0
    provider_count: int = 0


class HistoricalSearchResponse(BaseModel):
    query: str
    from_date: date | None
    to_date: date | None
    results: list[HistoricalArticleView]
    provider_statuses: list[HistoricalProviderStatus]
    duplicates_collapsed: int
    timeline_summary: HistoricalTimelineSummary | None = None
    generated_at: datetime


class ArchiveProviderName(StrEnum):
    WAYBACK = "wayback"
    COMMON_CRAWL = "common_crawl"


class ArchiveLookupCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    url: HttpUrl
    timestamp: datetime | None = None
    providers: list[ArchiveProviderName] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)


class ArchiveSnapshotView(BaseModel):
    provider: ArchiveProviderName
    original_url: str
    archived_url: str
    captured_at: datetime | None = None
    status_code: int | None = None
    mime_type: str | None = None
    digest: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ArchiveProviderStatus(BaseModel):
    provider: ArchiveProviderName
    success: bool
    result_count: int = 0
    error_code: str | None = None
    message: str | None = None


class ArchiveLookupResponse(BaseModel):
    url: str
    snapshots: list[ArchiveSnapshotView]
    provider_statuses: list[ArchiveProviderStatus]
    generated_at: datetime


HistoricalResultKind = Literal["news_article", "fact_check"]

class InternalHistoricalSearchCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=500)
    from_date: date | None = None
    to_date: date | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_dates(self) -> InternalHistoricalSearchCommand:
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date cannot be after to_date")
        return self


class InternalHistoricalMatchView(BaseModel):
    article_id: UUID
    event_id: UUID
    article_version_id: UUID
    version_number: int
    title: str
    url: str
    published_at: datetime | None
    retrieved_at: datetime
    snippet: str
    claim_count: int
    metadata: dict[str, object] = Field(default_factory=dict)


class InternalHistoricalSearchResponse(BaseModel):
    query: str
    from_date: date | None
    to_date: date | None
    results: list[InternalHistoricalMatchView]
    result_count: int
    event_count: int
    earliest_observed_at: datetime | None
    latest_observed_at: datetime | None
    generated_at: datetime

