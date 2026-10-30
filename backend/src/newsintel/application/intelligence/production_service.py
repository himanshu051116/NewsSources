from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel import __version__
from newsintel.application.intelligence.dto import (
    ProductionReadinessCommand,
    ProductionReadinessView,
    VerificationManifestBackfillCommand,
    VerificationManifestBackfillView,
    VerificationManifestView,
)
from newsintel.core.ids import uuid7
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION
from newsintel.domain.intelligence.production_readiness import (
    ReadinessInput,
    assess_production_readiness,
)
from newsintel.domain.intelligence.reproducibility import (
    VERIFICATION_MANIFEST_VERSION,
    build_verification_manifest,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleVersionModel,
    ClaimConflictResolutionModel,
    ClaimEvidenceLinkModel,
    ClaimReviewFlagModel,
    ClaimVerificationModel,
    EvidenceAuthorityProfileModel,
    EvidencePassageEvaluationModel,
    EvidenceRetrievalAttemptModel,
    EvidenceSearchRunModel,
    EvidenceSearchStoppingAssessmentModel,
    ProductionReadinessRunModel,
    VerificationQualityGateRunModel,
    VerificationRunManifestModel,
)


class VerificationManifestService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        claim_id: UUID,
        *,
        verification_id: UUID | None = None,
    ) -> VerificationManifestView | None:
        async with self._session_factory() as session, session.begin():
            claim = await session.get(ArticleClaimModel, claim_id)
            if claim is None:
                return None
            verification = await _resolve_verification(session, claim_id, verification_id)
            if verification is None:
                return None

            existing = await session.scalar(
                select(VerificationRunManifestModel).where(
                    VerificationRunManifestModel.verification_id == verification.id,
                    VerificationRunManifestModel.manifest_version == VERIFICATION_MANIFEST_VERSION,
                )
            )
            if existing is not None:
                return _manifest_view(existing)

            version = await session.get(ArticleVersionModel, claim.article_version_id)
            if version is None:
                raise RuntimeError("claim article version is missing")

            cutoff = verification.created_at
            passages = list(
                (
                    await session.scalars(
                        select(EvidencePassageEvaluationModel)
                        .where(
                            EvidencePassageEvaluationModel.claim_id == claim_id,
                            EvidencePassageEvaluationModel.retrieved_at <= cutoff,
                        )
                        .order_by(
                            EvidencePassageEvaluationModel.source_url,
                            EvidencePassageEvaluationModel.passage_sha256,
                        )
                    )
                ).all()
            )
            legacy_links = list(
                (
                    await session.scalars(
                        select(ClaimEvidenceLinkModel)
                        .where(
                            ClaimEvidenceLinkModel.claim_id == claim_id,
                            ClaimEvidenceLinkModel.retrieved_at <= cutoff,
                        )
                        .order_by(
                            ClaimEvidenceLinkModel.source_url,
                            ClaimEvidenceLinkModel.created_at,
                            ClaimEvidenceLinkModel.id,
                        )
                    )
                ).all()
            )
            search_runs = list(
                (
                    await session.scalars(
                        select(EvidenceSearchRunModel)
                        .where(
                            EvidenceSearchRunModel.claim_id == claim_id,
                            EvidenceSearchRunModel.started_at <= cutoff,
                        )
                        .order_by(EvidenceSearchRunModel.started_at, EvidenceSearchRunModel.id)
                    )
                ).all()
            )
            run_ids = [item.id for item in search_runs]
            attempts = []
            if run_ids:
                attempts = list(
                    (
                        await session.scalars(
                            select(EvidenceRetrievalAttemptModel)
                            .where(
                                EvidenceRetrievalAttemptModel.search_run_id.in_(run_ids),
                                EvidenceRetrievalAttemptModel.created_at <= cutoff,
                            )
                            .order_by(EvidenceRetrievalAttemptModel.created_at, EvidenceRetrievalAttemptModel.id)
                        )
                    ).all()
                )
            authority_ids = sorted({item.authority_profile_id for item in attempts}, key=str)
            authorities = []
            if authority_ids:
                authorities = list(
                    (
                        await session.scalars(
                            select(EvidenceAuthorityProfileModel)
                            .where(EvidenceAuthorityProfileModel.id.in_(authority_ids))
                            .order_by(EvidenceAuthorityProfileModel.id)
                        )
                    ).all()
                )
            conflict = await session.scalar(
                select(ClaimConflictResolutionModel)
                .where(
                    ClaimConflictResolutionModel.claim_id == claim_id,
                    ClaimConflictResolutionModel.created_at <= cutoff,
                )
                .order_by(ClaimConflictResolutionModel.created_at.desc())
                .limit(1)
            )
            stopping = await session.scalar(
                select(EvidenceSearchStoppingAssessmentModel)
                .where(
                    EvidenceSearchStoppingAssessmentModel.claim_id == claim_id,
                    EvidenceSearchStoppingAssessmentModel.created_at <= cutoff,
                )
                .order_by(EvidenceSearchStoppingAssessmentModel.created_at.desc())
                .limit(1)
            )
            review_flags = list(
                (
                    await session.scalars(
                        select(ClaimReviewFlagModel)
                        .where(
                            ClaimReviewFlagModel.claim_id == claim_id,
                            ClaimReviewFlagModel.created_at <= cutoff,
                        )
                        .order_by(ClaimReviewFlagModel.created_at, ClaimReviewFlagModel.id)
                    )
                ).all()
            )

            evidence_snapshot = [
                {
                    "id": str(item.id),
                    "source_url": item.source_url,
                    "source_type": item.source_type,
                    "evidence_class": item.evidence_class,
                    "passage_sha256": item.passage_sha256,
                    "stance": item.stance,
                    "stance_confidence": item.stance_confidence,
                    "temporal_relation": item.temporal_relation,
                    "published_at": _iso(item.published_at),
                    "retrieved_at": _iso(item.retrieved_at),
                    "independence_score": item.independence_score,
                    "primary_source": item.primary_source,
                    "assessor_version": item.assessor_version,
                    "lineage_key": _lineage_key(item.metadata_),
                }
                for item in passages
            ]
            evidence_snapshot.extend(
                {
                    "id": str(item.id),
                    "source_url": item.source_url,
                    "source_type": item.source_type,
                    "relationship": item.relationship,
                    "retrieved_at": _iso(item.retrieved_at),
                    "similarity_score": item.similarity_score,
                    "independence_score": item.independence_score,
                    "legacy_link": True,
                    "lineage_key": _lineage_key(item.metadata_),
                }
                for item in legacy_links
            )
            evidence_snapshot.sort(
                key=lambda item: (
                    str(item.get("source_url") or ""),
                    str(item.get("passage_sha256") or ""),
                    str(item.get("id") or ""),
                )
            )

            authority_snapshot = [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "evidence_class": item.evidence_class,
                    "jurisdiction": item.jurisdiction,
                    "language": item.language,
                    "base_url": item.base_url,
                    "allowed_domains": sorted(str(value) for value in item.allowed_domains),
                    "adapter_type": item.adapter_type,
                    "active": item.active,
                    "updated_at": _iso(item.updated_at),
                }
                for item in authorities
            ]
            authority_snapshot.sort(key=lambda item: str(item["id"]))

            decision_context: dict[str, object] = {
                "conflict": (
                    {
                        "id": str(conflict.id),
                        "state": conflict.state,
                        "confidence": conflict.confidence,
                        "resolver_version": conflict.resolver_version,
                        "created_at": _iso(conflict.created_at),
                    }
                    if conflict
                    else None
                ),
                "search_stopping": (
                    {
                        "id": str(stopping.id),
                        "decision": stopping.decision,
                        "completeness_score": stopping.completeness_score,
                        "methodology_version": stopping.methodology_version,
                        "created_at": _iso(stopping.created_at),
                    }
                    if stopping
                    else None
                ),
                "review_flags": [
                    {
                        "id": str(item.id),
                        "state": item.state,
                        "severity": item.severity,
                        "created_at": _iso(item.created_at),
                    }
                    for item in review_flags
                ],
            }
            payload: dict[str, object] = {
                "manifest_version": VERIFICATION_MANIFEST_VERSION,
                "code_version": __version__,
                "claim": {
                    "id": str(claim.id),
                    "article_id": str(claim.article_id),
                    "article_version_id": str(claim.article_version_id),
                    "claim_sha256": claim.claim_sha256,
                    "claim_text": claim.claim_text,
                    "extractor_version": claim.extractor_version,
                    "article_content_sha256": version.content_sha256,
                },
                "verification": {
                    "id": str(verification.id),
                    "label": verification.label,
                    "confidence_score": verification.confidence_score,
                    "methodology_version": verification.methodology_version,
                    "confidence_factors": verification.confidence_factors,
                    "reasoning_trace": verification.reasoning_trace,
                    "created_at": _iso(verification.created_at),
                },
                "evidence": evidence_snapshot,
                "authorities": authority_snapshot,
                "search_runs": [
                    {
                        "id": str(item.id),
                        "plan_key": item.plan_key,
                        "planner_version": item.planner_version,
                        "status": item.status,
                        "retrieval_complete": item.retrieval_complete,
                        "source_count": item.source_count,
                        "evidence_count": item.evidence_count,
                        "started_at": _iso(item.started_at),
                        "completed_at": _iso(item.completed_at),
                    }
                    for item in search_runs
                ],
                "retrieval_attempts": [
                    {
                        "id": str(item.id),
                        "search_run_id": str(item.search_run_id),
                        "authority_profile_id": str(item.authority_profile_id),
                        "candidate_url": item.candidate_url,
                        "status": item.status,
                        "http_status": item.http_status,
                        "body_sha256": item.body_sha256,
                        "created_at": _iso(item.created_at),
                    }
                    for item in attempts
                ],
                "decision_context": decision_context,
            }
            manifest = build_verification_manifest(payload)
            model = VerificationRunManifestModel(
                id=uuid7(),
                claim_id=claim_id,
                verification_id=verification.id,
                manifest_version=manifest.manifest_version,
                manifest_sha256=manifest.manifest_sha256,
                code_version=__version__,
                claim_sha256=claim.claim_sha256,
                article_content_sha256=version.content_sha256,
                evidence_snapshot=evidence_snapshot,
                authority_snapshot=authority_snapshot,
                decision_context=decision_context,
                payload=manifest.payload,
                created_at=datetime.now(UTC),
            )
            session.add(model)
            await session.flush()
            return _manifest_view(model)

    async def history(self, claim_id: UUID, *, limit: int = 50) -> list[VerificationManifestView] | None:
        async with self._session_factory() as session:
            if await session.get(ArticleClaimModel, claim_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(VerificationRunManifestModel)
                        .where(VerificationRunManifestModel.claim_id == claim_id)
                        .order_by(VerificationRunManifestModel.created_at.desc())
                        .limit(min(200, max(1, limit)))
                    )
                ).all()
            )
        return [_manifest_view(item) for item in rows]

    async def backfill(self, command: VerificationManifestBackfillCommand) -> VerificationManifestBackfillView:
        async with self._session_factory() as session:
            verification_rows = list(
                (
                    await session.execute(
                        select(ClaimVerificationModel.id, ClaimVerificationModel.claim_id)
                        .outerjoin(
                            VerificationRunManifestModel,
                            (VerificationRunManifestModel.verification_id == ClaimVerificationModel.id)
                            & (VerificationRunManifestModel.manifest_version == VERIFICATION_MANIFEST_VERSION),
                        )
                        .where(VerificationRunManifestModel.id.is_(None))
                        .order_by(ClaimVerificationModel.created_at.desc())
                        .limit(command.limit)
                    )
                ).all()
            )
        created = 0
        failed: list[dict[str, str]] = []
        for verification_id, claim_id in verification_rows:
            try:
                result = await self.create(claim_id, verification_id=verification_id)
                if result is not None:
                    created += 1
            except Exception as exc:  # individual historical rows must not abort the batch
                failed.append(
                    {
                        "verification_id": str(verification_id),
                        "claim_id": str(claim_id),
                        "error": type(exc).__name__,
                    }
                )
        return VerificationManifestBackfillView(
            requested_limit=command.limit,
            candidates=len(verification_rows),
            created=created,
            failed=len(failed),
            failures=failed,
            interpretation=(
                "Backfill creates immutable reproducibility manifests for existing verification revisions. "
                "It does not rerun or modify any historical verdict."
            ),
        )


class ProductionReadinessService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def assess(
        self,
        benchmark_set: str,
        command: ProductionReadinessCommand,
    ) -> ProductionReadinessView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            revision = await session.scalar(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            )
            quality_gate = await session.scalar(
                select(VerificationQualityGateRunModel)
                .where(VerificationQualityGateRunModel.benchmark_set == benchmark_set)
                .order_by(VerificationQualityGateRunModel.created_at.desc())
                .limit(1)
            )
            verification_ids = list(
                (
                    await session.scalars(
                        select(ClaimVerificationModel.id)
                        .order_by(ClaimVerificationModel.created_at.desc())
                        .limit(command.verification_sample_size)
                    )
                ).all()
            )
            manifest_count = 0
            if verification_ids:
                manifest_count = int(
                    await session.scalar(
                        select(func.count(VerificationRunManifestModel.id)).where(
                            VerificationRunManifestModel.verification_id.in_(verification_ids),
                            VerificationRunManifestModel.manifest_version == VERIFICATION_MANIFEST_VERSION,
                        )
                    )
                    or 0
                )
            open_review_flags = int(
                await session.scalar(
                    select(func.count(ClaimReviewFlagModel.id)).where(
                        ClaimReviewFlagModel.state == "review_required"
                    )
                )
                or 0
            )
            open_critical_flags = int(
                await session.scalar(
                    select(func.count(ClaimReviewFlagModel.id)).where(
                        ClaimReviewFlagModel.state == "review_required",
                        ClaimReviewFlagModel.severity == "critical",
                    )
                )
                or 0
            )
            active_authorities = int(
                await session.scalar(
                    select(func.count(EvidenceAuthorityProfileModel.id)).where(
                        EvidenceAuthorityProfileModel.active.is_(True)
                    )
                )
                or 0
            )
            manifest_coverage = (
                manifest_count / len(verification_ids) if verification_ids else 1.0
            )
            result = assess_production_readiness(
                ReadinessInput(
                    schema_matches=str(revision or "") == EXPECTED_SCHEMA_REVISION,
                    quality_gate_state=quality_gate.state if quality_gate else None,
                    verification_manifest_coverage=manifest_coverage,
                    open_critical_review_flags=open_critical_flags,
                    open_review_flags=open_review_flags,
                    active_authority_count=active_authorities,
                ),
                min_manifest_coverage=command.min_manifest_coverage,
                max_open_critical_reviews=command.max_open_critical_reviews,
                require_quality_gate_pass=command.require_quality_gate_pass,
                require_active_authority=command.require_active_authority,
            )
            thresholds = command.model_dump()
            checks = {
                **result.checks,
                "expected_schema_revision": EXPECTED_SCHEMA_REVISION,
                "observed_schema_revision": str(revision) if revision else None,
                "verification_sample_count": len(verification_ids),
                "verification_manifest_count": manifest_count,
                "latest_quality_gate_id": str(quality_gate.id) if quality_gate else None,
            }
            model = ProductionReadinessRunModel(
                id=uuid7(),
                benchmark_set=benchmark_set,
                methodology_version=result.methodology_version,
                state=result.state.value,
                failures=list(result.failures),
                warnings=list(result.warnings),
                checks=checks,
                thresholds=thresholds,
                metadata_={
                    "interpretation": result.interpretation,
                    "code_version": __version__,
                },
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _readiness_view(model)

    async def history(self, benchmark_set: str, *, limit: int = 50) -> list[ProductionReadinessView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(ProductionReadinessRunModel)
                        .where(ProductionReadinessRunModel.benchmark_set == benchmark_set)
                        .order_by(ProductionReadinessRunModel.created_at.desc())
                        .limit(min(200, max(1, limit)))
                    )
                ).all()
            )
        return [_readiness_view(item) for item in rows]


async def _resolve_verification(
    session: AsyncSession,
    claim_id: UUID,
    verification_id: UUID | None,
) -> ClaimVerificationModel | None:
    if verification_id is not None:
        model = await session.get(ClaimVerificationModel, verification_id)
        if model is None or model.claim_id != claim_id:
            return None
        return model
    return await session.scalar(
        select(ClaimVerificationModel)
        .where(ClaimVerificationModel.claim_id == claim_id)
        .order_by(ClaimVerificationModel.created_at.desc())
        .limit(1)
    )


def _manifest_view(model: VerificationRunManifestModel) -> VerificationManifestView:
    return VerificationManifestView(
        id=model.id,
        claim_id=model.claim_id,
        verification_id=model.verification_id,
        manifest_version=model.manifest_version,
        manifest_sha256=model.manifest_sha256,
        code_version=model.code_version,
        claim_sha256=model.claim_sha256,
        article_content_sha256=model.article_content_sha256,
        evidence_snapshot=list(model.evidence_snapshot),
        authority_snapshot=list(model.authority_snapshot),
        decision_context=dict(model.decision_context),
        payload=dict(model.payload),
        created_at=model.created_at,
        interpretation=(
            "The manifest is an immutable hash of the evidence and decision context available to this "
            "verification revision. It supports reproducibility; it does not independently establish truth."
        ),
    )


def _readiness_view(model: ProductionReadinessRunModel) -> ProductionReadinessView:
    return ProductionReadinessView(
        id=model.id,
        benchmark_set=model.benchmark_set,
        methodology_version=model.methodology_version,
        state=model.state,
        failures=list(model.failures),
        warnings=list(model.warnings),
        checks=dict(model.checks),
        thresholds=dict(model.thresholds),
        metadata=dict(model.metadata_),
        created_at=model.created_at,
        interpretation=str(model.metadata_.get("interpretation") or ""),
    )


def _lineage_key(metadata: dict[str, object] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("lineage_key") or metadata.get("evidence_lineage")
    return str(value) if value else None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
