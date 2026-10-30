from newsintel.domain.intelligence.quality import (
    ArticleQualitySignals,
    ClaimQualitySignal,
    assess_article_quality,
    evidence_domain,
)


def test_quality_profile_does_not_claim_truth_and_rewards_independent_evidence() -> None:
    assessment = assess_article_quality(
        ArticleQualitySignals(
            extraction_quality_score=0.95,
            extraction_warnings=(),
            version_count=2,
            latest_text="This story has been updated. " + "word " * 300,
            claims=(
                ClaimQualitySignal(
                    checkability_score=0.9,
                    claim_type="numeric",
                    verification_label="supported",
                    verification_confidence=0.88,
                    independent_evidence_count=2,
                    evidence_domains=("gov.example", "wire.example"),
                    primary_evidence_count=1,
                    temporally_resolved_evidence_count=2,
                    evidence_search_complete=True,
                ),
                ClaimQualitySignal(
                    checkability_score=0.8,
                    claim_type="temporal",
                    verification_label="disputed",
                    verification_confidence=0.72,
                    independent_evidence_count=1,
                    evidence_domains=("court.example",),
                    primary_evidence_count=1,
                    temporally_resolved_evidence_count=1,
                    evidence_search_complete=True,
                ),
            ),
        )
    )

    assert assessment.assessment_scope == "evidence_readiness_not_factual_truth"
    assert assessment.overall_evidence_readiness is not None
    assert assessment.overall_evidence_readiness > 0.75
    assert assessment.verified_claim_count == 2
    assert assessment.independent_evidence_links == 3
    assert assessment.evidence_domain_count == 3
    dimensions = {item.name: item for item in assessment.dimensions}
    assert dimensions["primary_evidence_coverage"].score == 1.0
    assert dimensions["evidence_search_completeness"].score == 1.0
    assert dimensions["temporal_context_resolution"].score == 1.0


def test_bootstrap_only_article_has_low_evidence_depth() -> None:
    assessment = assess_article_quality(
        ArticleQualitySignals(
            extraction_quality_score=0.9,
            extraction_warnings=(),
            latest_text="word " * 250,
            claims=(
                ClaimQualitySignal(
                    checkability_score=0.85,
                    claim_type="numeric",
                    verification_label="not_checkable",
                    verification_confidence=None,
                    independent_evidence_count=0,
                ),
            ),
        )
    )

    dimensions = {item.name: item for item in assessment.dimensions}
    assert dimensions["verification_coverage"].score == 0.0
    assert dimensions["independent_evidence_depth"].score == 0.0
    assert assessment.verified_claim_count == 0


def test_evidence_domain_normalizes_www() -> None:
    assert evidence_domain("https://www.Example.com/story") == "example.com"


def test_publisher_reliability_is_context_only_and_does_not_change_evidence_readiness() -> None:
    base = ArticleQualitySignals(
        extraction_quality_score=0.9,
        extraction_warnings=(),
        claims=(
            ClaimQualitySignal(
                checkability_score=0.9,
                claim_type="numeric",
                verification_label="supported",
                verification_confidence=0.9,
                independent_evidence_count=2,
                evidence_domains=("a.example", "b.example"),
                primary_evidence_count=1,
                temporally_resolved_evidence_count=2,
                evidence_search_complete=True,
            ),
        ),
        version_count=1,
        latest_text="A sufficiently complete article body " * 30,
    )
    low = assess_article_quality(
        ArticleQualitySignals(
            **{**base.__dict__} if hasattr(base, "__dict__") else {
                "extraction_quality_score": base.extraction_quality_score,
                "extraction_warnings": base.extraction_warnings,
                "claims": base.claims,
                "version_count": base.version_count,
                "latest_text": base.latest_text,
            },
            publisher_reliability_score=0.2,
            publisher_reliability_sample_size=100,
        )
    )
    high = assess_article_quality(
        ArticleQualitySignals(
            extraction_quality_score=base.extraction_quality_score,
            extraction_warnings=base.extraction_warnings,
            claims=base.claims,
            version_count=base.version_count,
            latest_text=base.latest_text,
            publisher_reliability_score=0.9,
            publisher_reliability_sample_size=100,
        )
    )
    assert low.overall_evidence_readiness == high.overall_evidence_readiness
    assert any(
        item.name == "publisher_historical_reliability_context" for item in low.dimensions
    )


def test_low_independence_links_do_not_inflate_evidence_depth() -> None:
    independent = assess_article_quality(
        ArticleQualitySignals(
            extraction_quality_score=0.9,
            extraction_warnings=(),
            latest_text="word " * 250,
            claims=(
                ClaimQualitySignal(
                    checkability_score=0.9,
                    claim_type="numeric",
                    verification_label="supported",
                    verification_confidence=0.9,
                    independent_evidence_count=2,
                    independent_evidence_weight=2.0,
                    evidence_domains=("a.example", "b.example"),
                ),
            ),
        )
    )
    copied = assess_article_quality(
        ArticleQualitySignals(
            extraction_quality_score=0.9,
            extraction_warnings=(),
            latest_text="word " * 250,
            claims=(
                ClaimQualitySignal(
                    checkability_score=0.9,
                    claim_type="numeric",
                    verification_label="supported",
                    verification_confidence=0.9,
                    independent_evidence_count=2,
                    independent_evidence_weight=0.2,
                    evidence_domains=("a.example", "b.example"),
                ),
            ),
        )
    )
    independent_dims = {item.name: item for item in independent.dimensions}
    copied_dims = {item.name: item for item in copied.dimensions}
    assert independent_dims["independent_evidence_depth"].score == 1.0
    assert copied_dims["independent_evidence_depth"].score == 0.1
    assert copied_dims["source_independence_integrity"].score == 0.1
    assert copied.overall_evidence_readiness < independent.overall_evidence_readiness
