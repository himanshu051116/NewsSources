from newsintel.domain.intelligence.dependency_propagation import classify_dependency_impact


def test_retraction_direct_dependency_is_high_and_stale() -> None:
    impact = classify_dependency_impact(
        correction_kind="retraction",
        claim_id="c2",
        claim_article_id="a2",
        via_article_id="a1",
        depth=1,
    )
    assert impact.severity == "high"
    assert "mark_verification_stale" in impact.actions
    assert "recompute_conflict" in impact.actions


def test_indirect_dependency_is_conservative() -> None:
    impact = classify_dependency_impact(
        correction_kind="factual_correction",
        claim_id="c3",
        claim_article_id="a3",
        via_article_id="a2",
        depth=2,
    )
    assert impact.severity == "low"
    assert "indirect dependency" in impact.rationale


def test_update_never_changes_verdict_automatically() -> None:
    impact = classify_dependency_impact(
        correction_kind="update",
        claim_id="c4",
        claim_article_id="a4",
        via_article_id="a1",
        depth=1,
    )
    assert impact.actions == ("review_claim",)
