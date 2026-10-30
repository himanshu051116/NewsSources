from datetime import UTC, datetime
from uuid import uuid4

from newsintel.application.articles.verification_service import _verification_evidence
from newsintel.infrastructure.db.models import ClaimEvidenceLinkModel


def _link(metadata: dict[str, object]) -> ClaimEvidenceLinkModel:
    return ClaimEvidenceLinkModel(
        id=uuid4(),
        claim_id=uuid4(),
        evidence_article_id=None,
        evidence_article_version_id=None,
        source_url="https://example.gov/order",
        source_type="court_order",
        relationship="support",
        retrieved_at=datetime.now(UTC),
        similarity_score=0.9,
        independence_score=0.9,
        metadata_=metadata,
        created_at=datetime.now(UTC),
    )


def test_source_type_alone_does_not_receive_primary_evidence_bonus() -> None:
    evidence = _verification_evidence(_link({"primary_source": True}))
    assert evidence.primary_source is False


def test_registry_validated_primary_source_receives_primary_evidence_bonus() -> None:
    evidence = _verification_evidence(
        _link({"primary_source_validated_by_registry": True})
    )
    assert evidence.primary_source is True
