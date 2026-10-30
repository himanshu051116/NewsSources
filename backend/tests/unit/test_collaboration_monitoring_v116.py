from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from newsintel.application.workspace_dto import (
    InvestigationMemberCreateCommand,
    SavedSearchMonitorCommand,
)
from newsintel.application.workspace_monitor_service import _search_link
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION, REQUIRED_V16_TABLES

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "newsintel"
ROUTES = SRC / "api" / "routes"


def test_collaboration_schema_head_and_tables_are_release_required() -> None:
    assert EXPECTED_SCHEMA_REVISION == "0033_grounded_news_explainer"
    required = set(REQUIRED_V16_TABLES)
    for name in (
        "investigations",
        "investigation_members",
        "investigation_activity",
        "workspace_monitors",
        "workspace_monitor_runs",
        "workspace_generated_alerts",
    ):
        assert name in required


def test_collaboration_migration_contains_expected_tables_and_single_parent() -> None:
    source = (ROOT / "migrations" / "versions" / "0025_collaboration_monitoring.py").read_text(encoding="utf-8")
    assert 'revision: str = "0025_collaboration_monitoring"' in source
    assert 'down_revision: str | None = "0024_analyst_workspace"' in source
    for name in (
        "investigation_members",
        "investigation_activity",
        "workspace_monitors",
        "workspace_monitor_runs",
        "workspace_generated_alerts",
    ):
        assert f'"{name}"' in source
    assert 'ondelete="CASCADE"' in source


def test_collaborator_roles_and_monitor_cadence_are_constrained() -> None:
    member = InvestigationMemberCreateCommand(email="Analyst@Example.com", access_role="editor")
    assert member.access_role == "editor"
    with pytest.raises(ValidationError):
        InvestigationMemberCreateCommand(email="x@example.com", access_role="owner")  # type: ignore[arg-type]
    monitor = SavedSearchMonitorCommand(enabled=True, cadence_minutes=60)
    assert monitor.cadence_minutes == 60
    with pytest.raises(ValidationError):
        SavedSearchMonitorCommand(enabled=True, cadence_minutes=59)


def test_workspace_api_exposes_members_activity_and_saved_search_monitor() -> None:
    source = (ROUTES / "workspace.py").read_text(encoding="utf-8")
    assert '/investigations/{investigation_id}/members' in source
    assert '/investigations/{investigation_id}/activity' in source
    assert '/saved-searches/{saved_search_id}/monitor' in source
    assert '/saved-searches/{saved_search_id}/monitor/runs' in source
    assert "WorkspacePermissionError" in source


def test_collaborative_dashboard_enforces_visible_access_boundaries() -> None:
    source = (ROUTES / "workspace_dashboard.py").read_text(encoding="utf-8")
    assert "Saved research" in source
    assert "Manage collaborators" in source
    assert "Reader access is view-only" in source
    assert "x.access_role!=='reader'" in source
    assert "exact verified email" in source.lower()
    assert "Scheduled search monitoring" in source
    assert "Recent evaluations" in source


def test_global_search_only_offers_editable_investigations_for_saved_search_attachment() -> None:
    source = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    assert "x.status==='active'&&x.access_role!=='reader'" in source


def test_workspace_alerts_do_not_depend_on_having_watchlists() -> None:
    source = (SRC / "application" / "workspace_service.py").read_text(encoding="utf-8")
    assert "if not watchlists:\n            return []" not in source
    assert "WorkspaceGeneratedAlertModel.owner_user_id == user_id" in source


def test_saved_search_activity_is_recorded_after_identifier_flush() -> None:
    source = (SRC / "application" / "workspace_service.py").read_text(encoding="utf-8")
    block = source[source.index("async def create_saved_search"):source.index("async def delete_saved_search")]
    assert block.index("await session.flush()") < block.index('action="saved_search_added"')


def test_monitor_worker_uses_fenced_leases_and_baseline_semantics() -> None:
    source = (SRC / "application" / "workspace_monitor_service.py").read_text(encoding="utf-8")
    assert "with_for_update(skip_locked=True)" in source
    assert "WorkspaceMonitorModel.lease_version == lease.lease_version" in source
    assert "new_keys = sorted(set(keys) - previous_keys) if previous is not None else []" in source
    worker = (SRC / "workers" / "workspace_monitor.py").read_text(encoding="utf-8")
    assert "lease_due" in worker
    assert "workspace_monitor_lease_seconds" in worker


def test_search_alert_link_preserves_query_and_type_without_string_concatenation() -> None:
    link = _search_link("coal & safety 100%", "claim")
    parsed = urlparse(link)
    assert parsed.path == "/search"
    params = parse_qs(parsed.query)
    assert params == {"q": ["coal & safety 100%"], "type": ["claim"]}


def test_release_launcher_includes_monitor_worker() -> None:
    # ROOT is backend; repository root is one level above.
    repo = ROOT.parent
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    launcher = (repo / "scripts" / "run-platform.ps1").read_text(encoding="utf-8")
    assert 'version = "1.25.0"' in text
    assert "newsintel-workspace-monitor" in text
    assert 'newsintel.workers.workspace_monitor' in launcher
