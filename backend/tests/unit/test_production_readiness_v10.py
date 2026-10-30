from newsintel.domain.intelligence.production_readiness import ReadinessInput, assess_production_readiness


def test_production_readiness_passes_only_with_reproducible_pipeline() -> None:
    result = assess_production_readiness(
        ReadinessInput(
            schema_matches=True,
            quality_gate_state="pass",
            verification_manifest_coverage=0.95,
            open_critical_review_flags=0,
            open_review_flags=0,
            active_authority_count=3,
        )
    )
    assert result.state == "pass"


def test_production_readiness_fails_on_schema_or_benchmark() -> None:
    result = assess_production_readiness(
        ReadinessInput(
            schema_matches=False,
            quality_gate_state="fail",
            verification_manifest_coverage=1.0,
            open_critical_review_flags=0,
            open_review_flags=0,
            active_authority_count=2,
        )
    )
    assert result.state == "fail"
    assert len(result.failures) >= 2


def test_noncritical_review_flags_warn_but_do_not_falsify_readiness() -> None:
    result = assess_production_readiness(
        ReadinessInput(
            schema_matches=True,
            quality_gate_state="pass",
            verification_manifest_coverage=1.0,
            open_critical_review_flags=0,
            open_review_flags=4,
            active_authority_count=1,
        )
    )
    assert result.state == "warn"
