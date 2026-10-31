"""Regression tests for v1.26 evidence and crawler-safety hotfix."""
from newsintel.adapters.http.crawl_policy import RobotsPolicy
from newsintel.domain.intelligence.claims import ClaimVerificationLabel, split_sentences
from newsintel.domain.intelligence.conflict_resolution import (
    ConflictEvidence, ConflictResolutionState, resolve_evidence_conflict,
)
from newsintel.domain.intelligence.evidence import _lexical_overlap
from newsintel.domain.intelligence.primary_evidence import plan_primary_evidence
from newsintel.domain.intelligence.stance import PassageStance, assess_evidence_stance
from newsintel.domain.intelligence.verification import (
    EvidenceStance, VerificationEvidence, verify_from_evidence,
)


def test_mixed_lineage_not_marked_supported() -> None:
    result = verify_from_evidence((
        VerificationEvidence(EvidenceStance.SUPPORT, 0.95, primary_source=True, lineage_key="authority:one"),
        VerificationEvidence(EvidenceStance.CONTRADICT, 0.90, primary_source=True, lineage_key="authority:one"),
    ))
    assert result.label is ClaimVerificationLabel.DISPUTED
    assert result.confidence_factors["independent_lineage_count"] == 1


def test_mixed_lineage_not_resolved_as_support() -> None:
    result = resolve_evidence_conflict((
        ConflictEvidence("support", 0.95, 0.95, primary_source=True, lineage_key="authority:one"),
        ConflictEvidence("contradict", 0.90, 0.95, primary_source=True, lineage_key="authority:one"),
    ))
    assert result.state is ConflictResolutionState.UNRESOLVED_CONFLICT
    assert result.independent_lineage_count == 1


def test_hindi_danda_boundaries() -> None:
    assert len(split_sentences("सरकार ने नई योजना घोषित की। मंत्री ने पुष्टि की।")) == 2


def test_hindi_denial_not_support() -> None:
    result = assess_evidence_stance(
        "राज्य सरकार ने शिक्षा नीति को मंजूरी दे दी है।",
        "राज्य सरकार ने शिक्षा नीति को मंजूरी नहीं दी है।",
    )
    assert result.stance is not PassageStance.SUPPORT


def test_hindi_lexical_overlap() -> None:
    assert _lexical_overlap("सरकार ने नई शिक्षा नीति की घोषणा की।", "सरकार ने नई नीति लागू की।") > 0.0


def test_hindi_evidence_plan_retains_query() -> None:
    result = plan_primary_evidence("राज्य सरकार ने शिक्षा नीति को मंजूरी नहीं दी है।")
    assert result.search_terms
    assert any("सरकार" in term or "शिक्षा" in term for term in result.search_terms)


def test_robots_longest_named_agent_wins() -> None:
    policy = RobotsPolicy.parse("""
User-agent: News
Allow: /private/

User-agent: NewsIntelligenceBot
Disallow: /private/
""")
    assert not policy.is_allowed("https://example.org/private/article", user_agent="NewsIntelligenceBot/0.1")


def test_english_negation_unchanged() -> None:
    result = assess_evidence_stance("The agency approved the proposal.", "The agency did not approve the proposal.")
    assert result.stance is PassageStance.CONTRADICT


def test_duplicate_wire_not_two_sources() -> None:
    result = verify_from_evidence((
        VerificationEvidence(EvidenceStance.SUPPORT, 0.8, lineage_key="wire:123"),
        VerificationEvidence(EvidenceStance.SUPPORT, 0.8, lineage_key="wire:123"),
    ))
    assert result.label is ClaimVerificationLabel.NOT_CHECKABLE
    assert result.confidence_factors["independent_lineage_count"] == 1
