from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

WorkspaceTargetType = Literal["event", "article", "claim"]
InvestigationAccessRole = Literal["reader", "editor", "owner"]
InvestigationMemberRole = Literal["reader", "editor"]


class InvestigationCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=2, max_length=240)
    description: str | None = Field(default=None, max_length=8_000)
    priority: Literal["low", "normal", "high", "critical"] = "normal"


class InvestigationUpdateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=2, max_length=240)
    description: str | None = Field(default=None, max_length=8_000)
    priority: Literal["low", "normal", "high", "critical"] | None = None
    status: Literal["active", "archived"] | None = None


class InvestigationMemberCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=320)
    access_role: InvestigationMemberRole = "reader"


class InvestigationMemberUpdateCommand(BaseModel):
    access_role: InvestigationMemberRole


class WorkspaceItemCreateCommand(BaseModel):
    item_type: WorkspaceTargetType
    item_id: UUID
    note: str | None = Field(default=None, max_length=2_000)


class AnalystNoteCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=20_000)
    target_type: WorkspaceTargetType | Literal["investigation"] = "investigation"
    target_id: UUID | None = None
    pinned: bool = False


class SavedSearchCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=200)
    query: str = Field(min_length=2, max_length=500)
    investigation_id: UUID | None = None
    filters: dict[str, object] = Field(default_factory=dict)


class SavedSearchMonitorCommand(BaseModel):
    enabled: bool = True
    cadence_minutes: int = Field(default=360, ge=60, le=10_080)


class WatchlistCreateCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4_000)


class WorkspaceAlertAcknowledgementCommand(BaseModel):
    acknowledged: bool = True


class WorkspaceItemView(BaseModel):
    id: UUID
    item_type: str
    item_id: UUID
    label: str
    note: str | None = None
    added_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)


class AnalystNoteView(BaseModel):
    id: UUID
    investigation_id: UUID | None
    author_user_id: UUID
    author_display_name: str | None = None
    target_type: str
    target_id: UUID | None
    body: str
    pinned: bool
    created_at: datetime
    updated_at: datetime


class WorkspaceMonitorView(BaseModel):
    id: UUID
    target_type: str
    target_id: UUID
    enabled: bool
    cadence_minutes: int
    next_run_at: datetime
    last_run_at: datetime | None
    last_success_at: datetime | None
    lease_version: int
    created_at: datetime
    updated_at: datetime


class WorkspaceMonitorRunView(BaseModel):
    id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    result_count: int
    new_result_count: int
    error: str | None = None


class SavedSearchView(BaseModel):
    id: UUID
    owner_user_id: UUID
    owner_display_name: str | None = None
    name: str
    query: str
    investigation_id: UUID | None
    filters: dict[str, object] = Field(default_factory=dict)
    monitor: WorkspaceMonitorView | None = None
    created_at: datetime
    updated_at: datetime


class InvestigationMemberView(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str | None
    verified_email: str | None
    access_role: InvestigationMemberRole
    added_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class InvestigationActivityView(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_display_name: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    summary: str
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class InvestigationSummaryView(BaseModel):
    id: UUID
    owner_user_id: UUID
    owner_display_name: str | None
    access_role: InvestigationAccessRole
    title: str
    description: str | None
    status: str
    priority: str
    item_count: int
    note_count: int
    saved_search_count: int
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class InvestigationDetailView(BaseModel):
    id: UUID
    current_user_id: UUID
    owner_user_id: UUID
    owner_display_name: str | None
    access_role: InvestigationAccessRole
    can_edit: bool
    can_manage_members: bool
    title: str
    description: str | None
    status: str
    priority: str
    items: list[WorkspaceItemView] = Field(default_factory=list)
    notes: list[AnalystNoteView] = Field(default_factory=list)
    saved_searches: list[SavedSearchView] = Field(default_factory=list)
    members: list[InvestigationMemberView] = Field(default_factory=list)
    activity: list[InvestigationActivityView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WatchlistSummaryView(BaseModel):
    id: UUID
    name: str
    description: str | None
    item_count: int
    created_at: datetime
    updated_at: datetime


class WatchlistDetailView(BaseModel):
    id: UUID
    name: str
    description: str | None
    items: list[WorkspaceItemView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WorkspaceAlertView(BaseModel):
    alert_key: str
    alert_type: str
    severity: str
    title: str
    detail: str
    target_type: str
    target_id: UUID
    occurred_at: datetime
    link: str
    watchlist_ids: list[UUID] = Field(default_factory=list)
    acknowledged: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkspaceOverviewView(BaseModel):
    investigations: list[InvestigationSummaryView] = Field(default_factory=list)
    watchlists: list[WatchlistSummaryView] = Field(default_factory=list)
    saved_searches: list[SavedSearchView] = Field(default_factory=list)
    alerts: list[WorkspaceAlertView] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class InvestigationManifestView(BaseModel):
    investigation_id: UUID
    title: str
    status: str
    priority: str
    generated_at: datetime
    methodology_version: str = "investigation-manifest-v2"
    items: list[dict[str, object]] = Field(default_factory=list)
    notes: list[AnalystNoteView] = Field(default_factory=list)
    saved_searches: list[SavedSearchView] = Field(default_factory=list)
    members: list[InvestigationMemberView] = Field(default_factory=list)


class WorkspaceMonitorLease(BaseModel):
    id: UUID
    owner_user_id: UUID
    target_type: str
    target_id: UUID
    cadence_minutes: int
    lease_owner: str
    lease_version: int
    lease_expires_at: datetime
