import pytest

from newsintel.adapters.http.crawl_policy import RobotsDeniedError, RobotsPolicy


def test_robots_longest_match_and_allow_wins_tie() -> None:
    policy = RobotsPolicy.parse(
        """
        User-agent: *
        Disallow: /private/
        Allow: /private/public/
        """
    )

    assert not policy.is_allowed(
        "https://example.com/private/story",
        user_agent="NewsIntelligenceBot/0.3",
    )
    assert policy.is_allowed(
        "https://example.com/private/public/story",
        user_agent="NewsIntelligenceBot/0.3",
    )


def test_specific_user_agent_group_overrides_wildcard_group() -> None:
    policy = RobotsPolicy.parse(
        """
        User-agent: *
        Disallow: /blocked-for-all

        User-agent: NewsIntelligenceBot
        Allow: /
        Disallow: /bot-private
        """
    )

    assert policy.is_allowed(
        "https://example.com/blocked-for-all",
        user_agent="NewsIntelligenceBot/0.3",
    )
    assert not policy.is_allowed(
        "https://example.com/bot-private/story",
        user_agent="NewsIntelligenceBot/0.3",
    )


def test_robots_supports_wildcards_and_end_anchor() -> None:
    policy = RobotsPolicy.parse(
        """
        User-agent: *
        Disallow: /*?preview=true$
        """
    )

    assert not policy.is_allowed(
        "https://example.com/story?preview=true",
        user_agent="NewsIntelligenceBot/0.3",
    )
    assert policy.is_allowed(
        "https://example.com/story?preview=true&x=1",
        user_agent="NewsIntelligenceBot/0.3",
    )


def test_robots_denied_error_is_permission_error() -> None:
    assert issubclass(RobotsDeniedError, PermissionError)
