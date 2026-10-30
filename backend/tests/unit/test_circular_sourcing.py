from newsintel.domain.intelligence.circularity import detect_circular_sourcing


def test_explicit_attribution_back_to_origin_is_circular() -> None:
    result = detect_circular_sourcing(
        "According to Example News, the ministry issued the order on Monday.",
        origin_publisher_name="Example News",
        origin_domain="example.com",
    )
    assert result.detected is True
    assert result.independence_cap == 0.15


def test_independent_mention_without_sourcing_language_is_not_circular() -> None:
    result = detect_circular_sourcing(
        "Example News and other outlets covered the policy debate last year.",
        origin_publisher_name="Example News",
    )
    assert result.detected is False
