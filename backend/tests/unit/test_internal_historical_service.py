from datetime import date

import pytest

from newsintel.application.historical.dto import InternalHistoricalSearchCommand
from newsintel.application.historical.internal_service import _escape_like, _snippet


def test_internal_historical_command_validates_date_range() -> None:
    with pytest.raises(ValueError):
        InternalHistoricalSearchCommand(
            query="policy",
            from_date=date(2026, 8, 2),
            to_date=date(2026, 8, 1),
        )


def test_like_escape_prevents_user_wildcards_from_changing_query_shape() -> None:
    assert _escape_like(r"100%_match") == r"100\%\_match"


def test_snippet_centers_search_term() -> None:
    text = "prefix " * 80 + "important historical phrase" + " suffix" * 80
    snippet = _snippet(text, "historical phrase", radius=40)

    assert "historical phrase" in snippet.lower()
    assert snippet.startswith("…")
    assert snippet.endswith("…")
