from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.articles.dto import (
    ClaimVerificationExecutionView,
    ClaimVerificationView,
)
from newsintel.core.ids import uuid7
from newsintel.domain.intelligence.verification import (
    EvidenceStance,
    VerificationEvidence,
    verify_from_evidence,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ClaimEvidenceLinkModel,
    ClaimVerificationModel,
)


class ClaimVerificationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def recompute(
        self,
        claim_id: UUID,
        *,
        retrieval_complete: bool = False,
    ) -> ClaimVerificationExecutionView | None:
        async with self._session_factory() as session, session.begin():
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            links = list(
                (
                    await session.scalars(
                        select(ClaimEvidenceLinkModel)
                        .where(ClaimEvidenceLinkModel.claim_id == claim_id)
                        .order_by(ClaimEvidenceLinkModel.retrieved_at)
                    )
                ).all()
            )
            evidence = tuple(_verification_evidence(link) for link in links)
            decision = verify_from_evidence(
                evidence,
                retrieval_complete=retrieval_complete,
            )
            now = datetime.now(UTC)
            model = ClaimVerificationModel(
                id=uuid7(),
                claim_id=claim_id,
                label=decision.label.value,
                confidence_score=decision.confidence_score,
                methodology_version=decision.methodology_version,
                confidence_factors={
                    **decision.confidence_factors,
                    "claim_type": claim.extraction_features.get("claim_type"),
                    "checkability_score": claim.extraction_features.get(
                        "checkability_score"
                    ),
                    "expected_primary_evidence": claim.extraction_features.get(
                        "expected_primary_evidence"
                    ),
                },
                reasoning_trace={
                    **decision.reasoning_trace,
                    "claim_family_key": claim.extraction_features.get("claim_family_key"),
                },
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return ClaimVerificationExecutionView(
                claim_id=claim_id,
                verification=ClaimVerificationView(
                    id=model.id,
                    label=model.label,
                    confidence_score=model.confidence_score,
                    methodology_version=model.methodology_version,
                    confidence_factors=model.confidence_factors,
                    reasoning_trace=model.reasoning_trace,
                    created_at=model.created_at,
                ),
            )


def _verification_evidence(link: ClaimEvidenceLinkModel) -> VerificationEvidence:
    relationship = link.relationship.lower().strip()
    if relationship == "origin" or link.source_type == "originating_article":
        stance = EvidenceStance.ORIGIN
    elif relationship in {"support", "supports", "supported", "corroborates"}:
        stance = EvidenceStance.SUPPORT
    elif relationship in {"contradict", "contradicts", "contradicted"}:
        stance = EvidenceStance.CONTRADICT
    elif relationship in {"dispute", "disputes", "disputed"}:
        stance = EvidenceStance.DISPUTE
    else:
        stance = EvidenceStance.CONTEXT

    metadata = link.metadata_
    raw_quality = metadata.get("evidence_quality")
    quality = float(raw_quality) if isinstance(raw_quality, int | float) else 1.0
    # v0.5 guardrail: a source type label alone is not enough for a primary-evidence
    # bonus. The evidence source must have been matched to an administrator-configured
    # authority profile during passage evaluation.
    primary_source = bool(metadata.get("primary_source_validated_by_registry"))
    lineage_key = metadata.get("lineage_key")
    if not isinstance(lineage_key, str) or not lineage_key:
        if link.evidence_article_id is not None:
            lineage_key = f"article:{link.evidence_article_id}"
        else:
            lineage_key = f"url:{link.source_url}"
    return VerificationEvidence(
        stance=stance,
        independence_score=link.independence_score,
        evidence_quality=quality,
        primary_source=primary_source,
        lineage_key=lineage_key,
    )
