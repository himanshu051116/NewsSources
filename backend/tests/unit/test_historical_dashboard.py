import pytest

from newsintel.api.routes.historical_dashboard import historical_research_dashboard


@pytest.mark.asyncio
async def test_historical_dashboard_uses_safe_dom_rendering() -> None:
    html = await historical_research_dashboard(object())  # type: ignore[arg-type]

    assert "/api/v1/historical/search" in html
    assert "/api/v1/historical/archives/lookup" in html
    assert "textContent" in html
    assert "innerHTML" not in html
    assert "noopener noreferrer" in html
