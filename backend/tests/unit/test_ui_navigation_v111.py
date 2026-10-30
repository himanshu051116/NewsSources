from newsintel.api.ui import nav_for_role


def test_viewer_navigation_matches_permissions() -> None:
    html = nav_for_role(active="news", role="viewer")
    assert 'href="/news"' in html
    assert 'href="/briefs"' in html
    assert 'href="/historical-research"' not in html
    assert 'href="/accuracy"' not in html
    assert 'href="/news-sources"' not in html
    assert 'href="/admin/access-console"' not in html


def test_source_manager_gets_analyst_and_source_navigation() -> None:
    html = nav_for_role(active="sources", role="source_manager")
    assert 'href="/historical-research"' in html
    assert 'href="/accuracy"' in html
    assert 'href="/news-sources"' in html
    assert 'href="/admin/access-console"' not in html


def test_owner_navigation_exposes_all_permitted_sections() -> None:
    html = nav_for_role(active="workspace", role="owner")
    assert 'href="/news"' in html
    assert 'href="/historical-research"' in html
    assert 'href="/accuracy"' in html
    assert 'href="/news-sources"' in html
    assert 'href="/admin/access-console"' in html
    assert 'href="/app" aria-current="page">Home</a>' in html


def test_mobile_navigation_is_not_truncated_for_administrator() -> None:
    html = nav_for_role(active="admin", role="administrator")
    mobile = html.split('class="mobile-nav"', 1)[1]
    assert '>Home</a>' in mobile
    assert '>News</a>' in mobile
    assert '>History & archives</a>' in mobile
    assert '>Verification review</a>' in mobile
    assert '>Sources</a>' in mobile
    assert '>Access</a>' in mobile
