from pathlib import Path

from newsintel.api.ui import nav_for_role
from newsintel.application.articles.query_service import _literal_like_pattern, _search_snippet

ROOT = Path(__file__).resolve().parents[2] / "src" / "newsintel" / "api" / "routes"


def test_viewer_navigation_exposes_corpus_search():
    html = nav_for_role(active="search", role="viewer")
    assert 'href="/search"' in html
    assert '>Search</a>' in html
    assert 'href="/events"' in html


def test_search_snippet_centers_matching_text():
    text = "A" * 150 + " Ministry of Coal issued the notification today. " + "B" * 150
    snippet = _search_snippet(text, "Ministry of Coal")
    assert "Ministry of Coal" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")



def test_search_like_pattern_escapes_wildcards():
    assert _literal_like_pattern("100%_done\\ok") == "%100\\%\\_done\\\\ok%"


def test_search_dashboard_contract_is_present():
    source = (ROOT / "search_dashboard.py").read_text()
    assert "Intelligence Search" in source
    assert "stored database content" in source
    assert "/api/v1/search" in source
    assert "Claim access required" in source


def test_event_dossier_ui_contract_is_present():
    source = (ROOT / "article_intelligence_dashboard.py").read_text()
    assert "Claim verification posture" in source
    assert "Source diversity" in source
    assert "Claims in current reporting" in source
    assert "/dossier" in source
    assert "Not a universal truth score" in source


def test_command_center_replaces_tile_only_workspace():
    source = (ROOT / "pages.py").read_text()
    assert "Command center" in source
    assert "Attention required" in source
    assert "Conflict / revision signals" in source
    assert "/api/v1/events?limit=40" in source
    assert "/api/v1/articles?limit=100" in source
