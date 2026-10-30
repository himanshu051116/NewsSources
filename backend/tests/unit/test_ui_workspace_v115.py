from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from newsintel.api.ui import nav_for_role
from newsintel.application.workspace_dto import InvestigationCreateCommand, WorkspaceItemCreateCommand
from newsintel.application.workspace_service import _correction_alerts

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "src" / "newsintel" / "api" / "routes"


def test_analyst_navigation_exposes_investigations() -> None:
    html = nav_for_role(active="investigations", role="analyst")
    assert 'href="/investigations"' in html
    assert '>Investigations</a>' in html
    viewer = nav_for_role(active="news", role="viewer")
    assert 'href="/investigations"' not in viewer


def test_workspace_dashboard_contract_is_connected() -> None:
    source = (ROUTES / "workspace_dashboard.py").read_text(encoding="utf-8")
    assert "saved research" in source.lower()
    assert "/api/v1/workspace/overview" in source
    assert "/api/v1/investigations" in source
    assert "/api/v1/watchlists" in source
    assert "Attention required" in source
    assert "Add tracked material" in source


def test_product_surfaces_link_into_workspace() -> None:
    article = (ROUTES / "article_intelligence_dashboard.py").read_text(encoding="utf-8")
    claim = (ROUTES / "claim_investigation_dashboard.py").read_text(encoding="utf-8")
    search = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    assert "add_type=article" in article
    assert "add_type=event" in article
    assert "add_type=claim" in claim
    assert "Save search" in search
    assert "/api/v1/saved-searches" in search


def test_workspace_api_and_migration_are_registered() -> None:
    main = (ROOT / "src" / "newsintel" / "main.py").read_text(encoding="utf-8")
    migration = (ROOT / "migrations" / "versions" / "0024_analyst_workspace.py").read_text(encoding="utf-8")
    assert "workspace_router" in main
    assert "workspace_dashboard_router" in main
    for table in (
        "investigations",
        "investigation_items",
        "analyst_notes",
        "saved_searches",
        "watchlists",
        "watchlist_items",
        "workspace_alert_acknowledgements",
    ):
        assert f'"{table}"' in migration


def test_workspace_commands_validate_types_and_priority() -> None:
    command = InvestigationCreateCommand(title="Coal regulation", priority="high")
    assert command.priority == "high"
    item = WorkspaceItemCreateCommand(item_type="claim", item_id=uuid4())
    assert item.item_type == "claim"


def test_correction_alerts_preserve_human_confirmed_kind() -> None:
    correction_id = uuid4()
    article_id = uuid4()
    event_id = uuid4()
    occurred = datetime.now(UTC)
    correction = SimpleNamespace(
        id=correction_id,
        article_id=article_id,
        event_id=event_id,
        correction_kind="factual_correction",
        note="Publisher corrected the allocation figure.",
        created_at=occurred,
    )
    alerts = _correction_alerts([correction], "article", article_id, "Allocation story", [uuid4()])
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_key == f"correction:{correction_id}"
    assert alert.severity == "high"
    assert alert.target_type == "article"
    assert alert.link == f"/articles/{article_id}/evolution"


def test_manifest_and_cache_guardrails_are_present() -> None:
    workspace = (ROUTES / "workspace.py").read_text(encoding="utf-8")
    main = (ROOT / "src" / "newsintel" / "main.py").read_text(encoding="utf-8")
    service = (ROOT / "src" / "newsintel" / "application" / "workspace_service.py").read_text(encoding="utf-8")
    assert '/investigations/{investigation_id}/manifest' in workspace
    assert 'content_sha256' in service
    assert 'lineage_key' in service
    assert '"/investigations", "/watchlists"' in main


def test_alert_deduplication_merges_watchlist_membership() -> None:
    source = (ROOT / "src" / "newsintel" / "application" / "workspace_service.py").read_text(encoding="utf-8")
    assert "{*existing.watchlist_ids, *alert.watchlist_ids}" in source
    assert 'alert.target_type == "article"' in source
