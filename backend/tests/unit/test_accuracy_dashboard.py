from types import SimpleNamespace

import pytest

from newsintel.api.routes.accuracy_dashboard import accuracy_dashboard
from newsintel.main import create_app


@pytest.mark.asyncio
async def test_accuracy_dashboard_exposes_abstention_and_scope_guardrails() -> None:
    auth = SimpleNamespace(role=SimpleNamespace(value="analyst"))
    html = await accuracy_dashboard(auth)  # type: ignore[arg-type]
    assert "Held-out validation" in html
    assert "Decided-case accuracy" in html
    assert "Decision coverage" in html
    assert "Unsafe high-confidence errors" in html
    assert "not a universal" in html


def test_accuracy_dashboard_route_registered() -> None:
    assert "/accuracy" in create_app().openapi()["paths"]
