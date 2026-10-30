from newsintel import __version__
from types import SimpleNamespace
from uuid import uuid4

import pytest

from newsintel.api.routes.article_intelligence_dashboard import (
    article_intelligence_dashboard,
    event_intelligence_dashboard,
)
from newsintel.api.routes.dashboard import news_sources_dashboard
from newsintel.api.routes.news_dashboard import news_dashboard
from newsintel.main import create_app
from newsintel.domain.access import AccessRole, ROLE_PERMISSIONS


def _auth(role: str = "viewer") -> SimpleNamespace:
    role_enum = AccessRole(role)
    permissions = {permission.value for permission in ROLE_PERMISSIONS[role_enum]}
    return SimpleNamespace(role=SimpleNamespace(value=role), permissions=permissions)


@pytest.mark.asyncio
async def test_news_ui_has_shared_shell_filters_and_human_labels() -> None:
    html = await news_dashboard(_auth())  # type: ignore[arg-type]
    assert "Latest news" in html
    assert "Past 24 hours" in html
    assert "Past 7 days" in html
    assert "Saved report" in html
    assert "current_only:true" in html
    assert "Historical linkage/coverage" not in html
    assert 'class="reader-nav"' in html
    assert '<aside class="app-sidebar"' not in html


@pytest.mark.asyncio
async def test_article_intelligence_degrades_optional_analyst_panels() -> None:
    html = await article_intelligence_dashboard(uuid4(), _auth())  # type: ignore[arg-type]
    assert "niOptional" in html
    assert "Analyst access is required" in html
    assert "Claims & verification" in html
    assert "Linked evidence" in html
    assert "Story timeline" in html
    assert "/events/${a.event_id}/intelligence" in html


@pytest.mark.asyncio
async def test_event_ui_is_human_facing() -> None:
    html = await event_intelligence_dashboard(uuid4(), _auth())  # type: ignore[arg-type]
    assert "Event dossier" in html
    assert "Material timeline" in html
    assert "Open story" in html


@pytest.mark.asyncio
async def test_sources_ui_separates_operations_from_news_reading() -> None:
    html = await news_sources_dashboard(_auth("source_manager"))  # type: ignore[arg-type]
    assert "Source operations" in html
    assert "Open news" in html
    assert "Publisher health" in html
    assert "News</h2>" not in html


def test_ui_routes_are_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/news" in paths
    assert "/articles/{article_id}/intelligence" in paths
    assert "/events/{event_id}/intelligence" in paths


def test_seamless_ui_release_version() -> None:
    assert __version__ == "1.25.0"
