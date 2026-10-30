from newsintel.domain.intelligence.claims import claim_features
from newsintel.domain.intelligence.primary_evidence import (
    EvidenceAuthorityClass,
    plan_primary_evidence,
)


def test_financial_claim_prefers_regulatory_filing_and_requires_counterevidence() -> None:
    claim = "Acme reported revenue rose 18% to ₹4,500 crore in 2026."
    plan = plan_primary_evidence(claim, extraction_features=claim_features(claim))

    assert plan.requirements[0].evidence_class is EvidenceAuthorityClass.REGULATORY_FILING
    assert EvidenceAuthorityClass.OFFICIAL_DATASET in {
        item.evidence_class for item in plan.requirements
    }
    assert plan.completeness_criteria["require_counterevidence_search"] is True
    assert plan.completeness_criteria["absence_is_not_contradiction"] is True


def test_legal_claim_requests_court_record() -> None:
    claim = "The High Court ordered the agency to suspend the notification on June 5, 2026."
    plan = plan_primary_evidence(claim, extraction_features=claim_features(claim))

    assert plan.requirements[0].evidence_class is EvidenceAuthorityClass.COURT_RECORD
    assert plan.requirements[0].required is True
