from datetime import UTC, datetime

import pytest

from newsintel.domain.acquisition.scheduling import current_sitemap


@pytest.mark.parametrize("url,expected", [
    ("https://news.example/sitemap.xml?dd=08&mm=01&yyyy=2008", False),
    ("https://news.example/sitemaps/06-07-2026.xml", False),
    ("https://news.example/sitemaps/22-10-2026.xml", True),
    ("https://news.example/archive/2026-10-20.xml", False),
    ("https://news.example/category/world/2026-October-1.xml", True),
    ("https://news.example/category/world/2026-September-1.xml", False),
    ("https://news.example/news-sitemap.xml", True),
    ("https://news.example/post-sitemap32.xml", True),
    ("https://news.example/sitemap/2026-99-99.xml", True),
])
def test_dated_archives_do_not_compete_with_current_maps(url, expected):
    assert current_sitemap(url, datetime(2026, 10, 23, 12, tzinfo=UTC)) is expected
