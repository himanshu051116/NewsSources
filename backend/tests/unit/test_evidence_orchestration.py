from newsintel.domain.intelligence.orchestration import (
    AuthorityOption,
    plan_authority_orchestration,
)


def test_planner_covers_required_classes_and_prefers_local_fit() -> None:
    result = plan_authority_orchestration(
        ("court_record", "official_dataset"),
        (
            AuthorityOption("global-court", "court_record", jurisdiction="global", authority_domain="g.example"),
            AuthorityOption("india-court", "court_record", jurisdiction="india", language="en", authority_domain="court.gov.in", prior_success_rate=0.8),
            AuthorityOption("stats", "official_dataset", jurisdiction="india", authority_domain="stats.gov.in", prior_success_rate=0.9),
        ),
        jurisdiction="india",
        language="en",
        max_authorities=2,
    )
    assert result.coverage_ratio == 1.0
    assert [item.authority_id for item in result.selections] == ["india-court", "stats"]
    assert result.uncovered_evidence_classes == ()


def test_planner_reports_uncovered_classes() -> None:
    result = plan_authority_orchestration(
        ("court_record", "regulatory_filing"),
        (AuthorityOption("court", "court_record"),),
        max_authorities=3,
    )
    assert result.coverage_ratio == 0.5
    assert result.uncovered_evidence_classes == ("regulatory_filing",)


def test_repeat_attempt_is_penalized_when_equivalent_option_exists() -> None:
    result = plan_authority_orchestration(
        ("official_dataset",),
        (
            AuthorityOption("old", "official_dataset", authority_domain="a.gov", prior_attempted=True),
            AuthorityOption("fresh", "official_dataset", authority_domain="b.gov"),
        ),
        max_authorities=1,
    )
    assert result.selections[0].authority_id == "fresh"
