from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "newsintel" / "api" / "routes"
BACKEND = Path(__file__).resolve().parents[2]


def test_article_evolution_dashboard_exposes_full_revision_workflow() -> None:
    source = (ROOT / "article_evolution_dashboard.py").read_text(encoding="utf-8")
    assert '"/articles/{article_id}/evolution"' in source
    assert "/historical/articles/${{articleId}}/versions" in source
    assert "/historical/articles/${{articleId}}/claim-history" in source
    assert "/historical/articles/${{articleId}}/corrections/detect" in source
    assert "/historical/articles/${{articleId}}/corrections" in source
    assert "/corrections/${{c.id}}/dependency-propagation" in source
    assert "Human confirmation" in source
    assert "does not silently change prior verification labels" in source
    assert "Detection confidence" in source
    assert "Downstream impact" in source


def test_article_intelligence_links_to_evolution_for_analyst_roles() -> None:
    source = (ROOT / "article_intelligence_dashboard.py").read_text(encoding="utf-8")
    assert "Article evolution" in source
    assert "Permission.CLAIMS_VIEW.value in auth.permissions" in source
    assert "Historical context" in source


def test_article_evolution_route_is_registered() -> None:
    source = (BACKEND / "src" / "newsintel" / "main.py").read_text(encoding="utf-8")
    assert "article_evolution_dashboard_router" in source
    assert "app.include_router(article_evolution_dashboard_router)" in source
