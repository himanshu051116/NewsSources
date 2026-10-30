"""User-facing wording and navigation tests for the refined v1.25 UI."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from newsintel.api.ui import nav_for_role, render_app_page
from newsintel.api.routes.briefing_dashboard import event_briefing_dashboard

ROUTES = Path(__file__).resolve().parents[2] / "src" / "newsintel" / "api" / "routes"


def test_grouped_navigation_is_permission_derived_and_mobile_complete() -> None:
    viewer = nav_for_role(active="news", role="viewer")
    assert 'href="/search"' in viewer
    assert 'href="/news-sources"' not in viewer
    assert 'href="/admin/access-console"' not in viewer
    admin = nav_for_role(active="admin", role="administrator")
    mobile = admin.split('class="mobile-nav"', 1)[1]
    assert 'aria-hidden="true" inert' in mobile
    assert '>Sources</a>' in mobile
    assert '>Access</a>' in mobile
    assert 'aria-current="page"' in mobile


def test_shared_layout_has_explanatory_legend_and_accessible_drawer() -> None:
    html = render_app_page(title="Reports", body="<p>Example</p>", role="analyst", active="news")
    assert 'id="openMobileMenu"' in html
    assert 'aria-controls="mobileMenu"' in html
    assert 'aria-expanded="false"' in html
    assert 'id="navBackdrop"' in html
    assert 'How to read evidence and status labels' in html
    assert 'not a universal truth certificate' in html
    assert 'id="themeToggle"' in html


@pytest.mark.asyncio
async def test_briefing_shows_readable_references_instead_of_raw_ids() -> None:
    html = await event_briefing_dashboard(uuid4(), SimpleNamespace(role=SimpleNamespace(value="analyst"), permissions={"claims:view", "claims:verify"}))
    assert 'Sources and references' in html
    assert 'id="source-reference-${i+1}"' in html
    assert 'href="#source-reference-${r.index}"' in html
    assert 'Record identifier' in html
    assert 'A cited report is not automatically an independently verified fact' in html
    assert "niEsc(item.text)" in html


def test_copy_describes_measured_coverage_without_ai_hype() -> None:
    home = (ROUTES / "pages.py").read_text(encoding="utf-8")
    news = (ROUTES / "news_dashboard.py").read_text(encoding="utf-8")
    search = (ROUTES / "search_dashboard.py").read_text(encoding="utf-8")
    assert "latest 40 events and 100 reports" in home
    assert "Search the archive" in news
    assert "Search headlines already loaded" in news
    assert "Publication dates checked" in news
    assert "Results as of" in search
    assert "AI-powered" not in (home + news + search)


@pytest.mark.asyncio
async def test_article_evolution_renders_js_destructuring_safely() -> None:
    from newsintel.api.routes.article_evolution_dashboard import article_evolution_dashboard
    html = await article_evolution_dashboard(uuid4(), SimpleNamespace(role=SimpleNamespace(value="analyst"), permissions={"claims:view", "claims:verify"}))
    assert "groups.map(({correction:c,run:p})=>" in html
    assert "Correction dependency impact" in html


@pytest.mark.asyncio
async def test_sensitive_admin_and_publisher_actions_use_dialogs() -> None:
    from newsintel.api.routes.pages import access_console
    from newsintel.api.routes.dashboard import news_sources_dashboard
    auth = SimpleNamespace(role=SimpleNamespace(value="administrator"))
    admin_html = await access_console(auth)
    source_html = await news_sources_dashboard(auth)
    assert 'id="accessActionDialog"' in admin_html
    assert 'id="confirmAccessAction"' in admin_html
    assert 'id="disablePublisherDialog"' in source_html
    assert 'id="confirmDisablePublisher"' in source_html
    assert "prompt(" not in admin_html and "confirm(" not in source_html
