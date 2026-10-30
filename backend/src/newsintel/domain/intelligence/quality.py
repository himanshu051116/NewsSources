from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from newsintel.domain.intelligence.claims import ClaimVerificationLabel

QUALITY_METHODOLOGY_VERSION = "evidence-readiness-v4"


class QualityStatus(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient_data"


@dataclass(frozen=True, slots=True)
class ClaimQualitySignal:
    checkability_score: float | None
    claim_type: str | None
    verification_label: str | None
    verification_confidence: float | None
    independent_evidence_count: int
    independent_evidence_weight: float | None = None
    evidence_domains: tuple[str, ...] = ()
    primary_evidence_count: int = 0
    temporally_resolved_evidence_count: int = 0
    evidence_search_complete: bool = False


@dataclass(frozen=True, slots=True)
class ArticleQualitySignals:
    extraction_quality_score: float | None
    extraction_warnings: tuple[str, ...]
    claims: tuple[ClaimQualitySignal, ...]
    version_count: int = 1
    latest_text: str = ""
    publisher_reliability_score: float | None = None
    publisher_reliability_sample_size: int | None = None


@dataclass(frozen=True, slots=True)
class QualityDimension:
    name: str
    score: float | None
    status: QualityStatus
    explanation: str
    sample_size: int | None = None


@dataclass(frozen=True, slots=True)
class ArticleQualityAssessment:
    methodology_version: str
    assessment_scope: str
    overall_evidence_readiness: float | None
    dimensions: tuple[QualityDimension, ...]
    claim_count: int
    checkable_claim_count: int
    verified_claim_count: int
    independent_evidence_links: int
    evidence_domain_count: int


def assess_article_quality(signals: ArticleQualitySignals) -> ArticleQualityAssessment:
    """Score how audit-ready an article is without pretending to score factual truth.

    The output is deliberately evidence/readiness oriented. A high score means the system
    has extractable, checkable claims and sufficient independent evidence to assess them;
    it does *not* mean every claim is true.
    """

    claims = signals.claims
    checkable = [
        claim
        for claim in claims
        if claim.checkability_score is not None and claim.checkability_score >= 0.5
    ]
    verified = [
        claim
        for claim in claims
        if claim.verification_label
        and claim.verification_label != ClaimVerificationLabel.NOT_CHECKABLE.value
    ]
    independent_links = sum(max(0, claim.independent_evidence_count) for claim in claims)
    evidence_domains = {
        domain
        for claim in claims
        for domain in claim.evidence_domains
        if domain
    }

    extraction_score = _extraction_score(signals)
    checkability_score = (
        sum(float(claim.checkability_score or 0.0) for claim in claims) / len(claims)
        if claims
        else None
    )
    verification_coverage = len(verified) / len(claims) if claims else None
    evidence_depth = (
        sum(min(1.0, _effective_independence_weight(claim) / 2) for claim in claims) / len(claims)
        if claims
        else None
    )
    evidence_diversity = (
        min(1.0, len(evidence_domains) / 3)
        if independent_links > 0
        else (0.0 if claims else None)
    )
    source_independence_integrity = (
        min(1.0, sum(_effective_independence_weight(claim) for claim in claims) / independent_links)
        if independent_links > 0
        else (0.0 if claims else None)
    )
    evidence_consistency = _verification_confidence_score(verified)
    primary_evidence_coverage = (
        sum(claim.primary_evidence_count > 0 for claim in checkable) / len(checkable)
        if checkable
        else None
    )
    evidence_search_completeness = (
        sum(claim.evidence_search_complete for claim in checkable) / len(checkable)
        if checkable
        else None
    )
    temporal_context_resolution = (
        sum(
            min(1.0, claim.temporally_resolved_evidence_count / max(1, claim.independent_evidence_count))
            for claim in claims
            if claim.independent_evidence_count > 0
        )
        / len([claim for claim in claims if claim.independent_evidence_count > 0])
        if any(claim.independent_evidence_count > 0 for claim in claims)
        else (0.0 if claims else None)
    )
    revision_transparency = _revision_transparency(signals)

    dimensions = (
        _dimension(
            "extraction_integrity",
            extraction_score,
            "Quality and completeness of the extracted article body.",
            1,
        ),
        _dimension(
            "claim_checkability",
            checkability_score,
            "How specifically the article's extracted claims can be tested against evidence.",
            len(claims),
        ),
        _dimension(
            "verification_coverage",
            verification_coverage,
            "Share of extracted claims with a non-bootstrap verification conclusion.",
            len(claims),
        ),
        _dimension(
            "independent_evidence_depth",
            evidence_depth,
            "Independent evidence attached per claim; originating articles do not count.",
            len(claims),
        ),
        _dimension(
            "evidence_source_diversity",
            evidence_diversity,
            "Distinct independent evidence domains represented across the article's claims.",
            independent_links,
        ),
        _dimension(
            "source_independence_integrity",
            source_independence_integrity,
            (
                "Effective corroboration weight after syndication, same-source, ownership and "
                "explicit circular-sourcing caps; evidence stance is not changed by these caps."
            ),
            independent_links,
        ),
        _dimension(
            "verification_confidence",
            evidence_consistency,
            "Average confidence of completed claim verifications, when available.",
            len(verified),
        ),
        _dimension(
            "primary_evidence_coverage",
            primary_evidence_coverage,
            "Share of checkable claims backed by at least one registry-validated primary record.",
            len(checkable),
        ),
        _dimension(
            "evidence_search_completeness",
            evidence_search_completeness,
            "Share of checkable claims whose evidence-search run was explicitly completed, including counterevidence search requirements.",
            len(checkable),
        ),
        _dimension(
            "temporal_context_resolution",
            temporal_context_resolution,
            "How often attached evidence has an explicit temporal relation, reducing false contradictions across different as-of times.",
            independent_links,
        ),
        _dimension(
            "revision_transparency",
            revision_transparency,
            "Whether revisions are observable and correction/update language is retained.",
            signals.version_count,
        ),
        _dimension(
            "publisher_historical_reliability_context",
            signals.publisher_reliability_score,
            (
                "Context-only Bayesian history from mature verified claims for this publisher. "
                "It is not included in the article evidence-readiness score and must not replace "
                "claim-level evidence."
            ),
            signals.publisher_reliability_sample_size,
        ),
    )

    weighted: list[tuple[float, float]] = []
    weights = {
        "extraction_integrity": 0.12,
        "claim_checkability": 0.12,
        "verification_coverage": 0.14,
        "independent_evidence_depth": 0.14,
        "evidence_source_diversity": 0.04,
        "source_independence_integrity": 0.06,
        "verification_confidence": 0.10,
        "primary_evidence_coverage": 0.12,
        "evidence_search_completeness": 0.10,
        "temporal_context_resolution": 0.05,
        "revision_transparency": 0.05,
        "publisher_historical_reliability_context": 0.0,
    }
    for dimension in dimensions:
        if dimension.score is not None:
            weighted.append((dimension.score, weights[dimension.name]))
    total_weight = sum(weight for _, weight in weighted)
    overall = (
        sum(score * weight for score, weight in weighted) / total_weight
        if total_weight > 0
        else None
    )

    return ArticleQualityAssessment(
        methodology_version=QUALITY_METHODOLOGY_VERSION,
        assessment_scope="evidence_readiness_not_factual_truth",
        overall_evidence_readiness=_round(overall),
        dimensions=dimensions,
        claim_count=len(claims),
        checkable_claim_count=len(checkable),
        verified_claim_count=len(verified),
        independent_evidence_links=independent_links,
        evidence_domain_count=len(evidence_domains),
    )


def evidence_domain(url: str) -> str | None:
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _extraction_score(signals: ArticleQualitySignals) -> float | None:
    if signals.extraction_quality_score is not None:
        value = float(signals.extraction_quality_score)
        # Existing extractors may use either a 0..1 or 0..100 convention.
        if value > 1.0:
            value /= 100.0
        return _clamp(value)
    if not signals.latest_text:
        return 0.0
    penalty = min(0.8, 0.12 * len(signals.extraction_warnings))
    word_count = len(signals.latest_text.split())
    base = 0.9 if word_count >= 250 else 0.75 if word_count >= 100 else 0.55
    return _clamp(base - penalty)


def _verification_confidence_score(
    verified: list[ClaimQualitySignal],
) -> float | None:
    values = [
        float(claim.verification_confidence)
        for claim in verified
        if claim.verification_confidence is not None
    ]
    if not values:
        return None
    normalized = [value / 100 if value > 1.0 else value for value in values]
    return _clamp(sum(normalized) / len(normalized))


def _revision_transparency(signals: ArticleQualitySignals) -> float:
    if signals.version_count <= 1:
        # No revision observed is neutral rather than evidence of poor transparency.
        return 0.5
    lowered = signals.latest_text.lower()
    correction_markers = (
        "correction:",
        "corrected on",
        "this article was corrected",
        "updated on",
        "this story has been updated",
    )
    if any(marker in lowered for marker in correction_markers):
        return 1.0
    # Version history itself remains auditable even if the publisher did not label it.
    return 0.65


def _dimension(
    name: str,
    score: float | None,
    explanation: str,
    sample_size: int | None,
) -> QualityDimension:
    normalized = _round(score)
    return QualityDimension(
        name=name,
        score=normalized,
        status=_status(normalized),
        explanation=explanation,
        sample_size=sample_size,
    )


def _status(score: float | None) -> QualityStatus:
    if score is None:
        return QualityStatus.INSUFFICIENT
    if score >= 0.8:
        return QualityStatus.STRONG
    if score >= 0.55:
        return QualityStatus.MODERATE
    return QualityStatus.WEAK


def _round(value: float | None) -> float | None:
    return round(_clamp(value), 4) if value is not None else None


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _effective_independence_weight(claim: ClaimQualitySignal) -> float:
    if claim.independent_evidence_weight is None:
        # Backward-compatible default for callers created before v0.7. Production callers now
        # pass the sum of lineage/ownership/circularity-adjusted link weights explicitly.
        return float(max(0, claim.independent_evidence_count))
    return max(0.0, float(claim.independent_evidence_weight))
