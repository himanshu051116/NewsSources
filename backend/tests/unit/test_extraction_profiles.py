from newsintel.application.articles.extraction_profiles import (
    _recommend_method,
    _updated_method_stats,
)


def test_extraction_profile_recommendation_requires_repeated_quality_evidence() -> None:
    stats: dict[str, object] = {}
    for _ in range(4):
        stats = _updated_method_stats(
            stats,
            {"visible_text_blocks": 0.55, "hydration_json_body": 0.86},
            selected_method="hydration_json_body",
        )
    assert _recommend_method(stats) is None

    stats = _updated_method_stats(
        stats,
        {"visible_text_blocks": 0.55, "hydration_json_body": 0.86},
        selected_method="hydration_json_body",
    )
    assert _recommend_method(stats) == "hydration_json_body"


def test_extraction_profile_does_not_recommend_near_tied_methods() -> None:
    stats: dict[str, object] = {}
    for _ in range(6):
        stats = _updated_method_stats(
            stats,
            {"visible_text_blocks": 0.78, "hydration_json_body": 0.80},
            selected_method="hydration_json_body",
        )
    assert _recommend_method(stats) is None
