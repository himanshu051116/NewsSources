from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.articles.dto import IntelligenceSearchView
from newsintel.application.search.dto import (
    SearchDeploymentActionView,
    SearchDeploymentConfigCommand,
    SearchDeploymentConfigView,
    SearchDeploymentOutcomeCommand,
    SearchDeploymentRollbackCommand,
    SearchDeploymentStatusView,
    SearchDeploymentTelemetryView,
)
from newsintel.application.search.rerank_service import SemanticArticleReranker, SemanticRerankUnavailableError
from newsintel.application.search.service import IntelligenceSearchService, SearchFilters, _search_fingerprint
from newsintel.core.ids import uuid7
from newsintel.domain.search.deployment import (
    SearchCircuitBreakerPolicy,
    SearchDeploymentState,
    SearchDeploymentVariant,
    assess_circuit_breaker_summary,
    assigned_to_canary,
    deterministic_bucket,
)
from newsintel.infrastructure.db.models import (
    SearchDeploymentActionModel,
    SearchDeploymentModel,
    SearchDeploymentObservationModel,
    SearchDeploymentOutcomeModel,
    SearchPromotionDecisionModel,
    SearchPromotionEvaluationModel,
)


class SearchDeploymentValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SearchDeploymentPlan:
    deployment_id: UUID | None
    rollout_salt: str
    state: str
    bucket: int
    assigned_variant: str
    eligible: bool
    reason: str | None = None


class SearchDeploymentControlService:
    DEPLOYMENT_NAME = "production"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def status(self) -> SearchDeploymentStatusView:
        async with self._session_factory() as session:
            deployment = await self._deployment(session)
            config = self._config_view(deployment)
            approval_active = False
            if deployment is not None and deployment.promotion_decision_id is not None:
                approval_active = await self._active_approved_evaluation(session, deployment.promotion_decision_id) is not None
            config = config.model_copy(update={"approval_active": approval_active})
            telemetry = await self._telemetry(session, deployment)
            actions = await self._actions(session, deployment, limit=12)
            breaker = self._breaker_from_telemetry(config, telemetry)
            reasons = list(breaker.reasons)
            blocked_approval = config.state in {SearchDeploymentState.SHADOW.value, SearchDeploymentState.CANARY.value} and not approval_active
            if blocked_approval:
                reasons.append("configured promotion approval is no longer the active approve_candidate decision")
        return SearchDeploymentStatusView(
            config=config,
            telemetry=telemetry,
            circuit_breaker_state="blocked" if blocked_approval else ("tripped" if breaker.should_pause else "healthy"),
            circuit_breaker_reasons=reasons,
            latest_actions=actions,
            production_mode=(
                "hybrid_canary"
                if config.state == SearchDeploymentState.CANARY.value and config.target_percent > 0 and approval_active
                else "lexical"
            ),
        )

    async def configure(
        self,
        command: SearchDeploymentConfigCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchDeploymentStatusView:
        requested_state = SearchDeploymentState(command.state)
        if requested_state in {SearchDeploymentState.OFF, SearchDeploymentState.PAUSED}:
            target_percent = 0.0
        else:
            target_percent = command.target_percent
        if requested_state == SearchDeploymentState.CANARY and target_percent <= 0:
            raise SearchDeploymentValidationError("CANARY requires target_percent greater than 0")
        if requested_state == SearchDeploymentState.SHADOW and target_percent <= 0:
            raise SearchDeploymentValidationError("SHADOW requires target_percent greater than 0")

        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            deployment = await self._deployment(session, for_update=True)
            previous_state = deployment.state if deployment is not None else SearchDeploymentState.OFF.value
            previous_target = deployment.target_percent if deployment is not None else 0.0
            benchmark_set: str | None = None
            if requested_state in {SearchDeploymentState.SHADOW, SearchDeploymentState.CANARY}:
                if command.promotion_decision_id is None:
                    raise SearchDeploymentValidationError(
                        "SHADOW/CANARY requires a human approve_candidate decision from a PASS promotion gate"
                    )
                evaluation = await self._active_approved_evaluation(session, command.promotion_decision_id)
                if evaluation is None:
                    raise SearchDeploymentValidationError(
                        "promotion decision is not the latest approve_candidate decision on a PASS gate evaluation"
                    )
                benchmark_set = evaluation.benchmark_set
            elif command.promotion_decision_id is not None:
                evaluation = await self._active_approved_evaluation(session, command.promotion_decision_id)
                if evaluation is None:
                    raise SearchDeploymentValidationError("promotion decision is no longer an active approve_candidate decision")
                benchmark_set = evaluation.benchmark_set

            if deployment is None:
                deployment = SearchDeploymentModel(
                    id=uuid7(),
                    name=self.DEPLOYMENT_NAME,
                    state=requested_state.value,
                    target_percent=target_percent,
                    promotion_decision_id=command.promotion_decision_id,
                    benchmark_set=benchmark_set,
                    rollout_salt=secrets.token_hex(16),
                    max_hybrid_p95_ms=command.max_hybrid_p95_ms,
                    max_hybrid_error_rate=command.max_hybrid_error_rate,
                    min_hybrid_samples=command.min_hybrid_samples,
                    circuit_window_minutes=command.circuit_window_minutes,
                    auto_pause=command.auto_pause,
                    configured_by_user_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(deployment)
                await session.flush()
            else:
                deployment.state = requested_state.value
                deployment.target_percent = target_percent
                deployment.promotion_decision_id = command.promotion_decision_id
                deployment.benchmark_set = benchmark_set
                deployment.max_hybrid_p95_ms = command.max_hybrid_p95_ms
                deployment.max_hybrid_error_rate = command.max_hybrid_error_rate
                deployment.min_hybrid_samples = command.min_hybrid_samples
                deployment.circuit_window_minutes = command.circuit_window_minutes
                deployment.auto_pause = command.auto_pause
                deployment.configured_by_user_id = actor_user_id
                deployment.updated_at = now
            session.add(
                SearchDeploymentActionModel(
                    id=uuid7(),
                    deployment_id=deployment.id,
                    action="configure",
                    previous_state=previous_state,
                    new_state=requested_state.value,
                    target_percent=target_percent,
                    rationale=command.rationale,
                    metadata_={"previous_target_percent": previous_target, "benchmark_set": benchmark_set},
                    actor_user_id=actor_user_id,
                    created_at=now,
                )
            )
        return await self.status()

    async def rollback(
        self,
        command: SearchDeploymentRollbackCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchDeploymentStatusView:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            deployment = await self._deployment(session, for_update=True)
            if deployment is None:
                return await self.status()
            previous_state = deployment.state
            previous_target = deployment.target_percent
            deployment.state = SearchDeploymentState.PAUSED.value
            deployment.target_percent = 0.0
            deployment.configured_by_user_id = actor_user_id
            deployment.updated_at = now
            session.add(
                SearchDeploymentActionModel(
                    id=uuid7(),
                    deployment_id=deployment.id,
                    action="manual_pause",
                    previous_state=previous_state,
                    new_state=SearchDeploymentState.PAUSED.value,
                    target_percent=0.0,
                    rationale=command.rationale,
                    metadata_={"previous_target_percent": previous_target},
                    actor_user_id=actor_user_id,
                    created_at=now,
                )
            )
        return await self.status()

    async def plan(self, *, subject_user_id: UUID, result_type: str) -> SearchDeploymentPlan:
        async with self._session_factory() as session:
            deployment = await self._deployment(session)
            if deployment is None:
                return SearchDeploymentPlan(None, "", SearchDeploymentState.OFF.value, 0, SearchDeploymentVariant.LEXICAL.value, False, "deployment_not_configured")
            bucket = deterministic_bucket(subject_id=subject_user_id, salt=deployment.rollout_salt)
            if deployment.state not in {SearchDeploymentState.SHADOW.value, SearchDeploymentState.CANARY.value}:
                return SearchDeploymentPlan(deployment.id, deployment.rollout_salt, deployment.state, bucket, SearchDeploymentVariant.LEXICAL.value, False, "deployment_not_active")
            if result_type != "article":
                return SearchDeploymentPlan(deployment.id, deployment.rollout_salt, deployment.state, bucket, SearchDeploymentVariant.LEXICAL.value, False, "article_only_canary")
            if deployment.promotion_decision_id is None or await self._active_approved_evaluation(session, deployment.promotion_decision_id) is None:
                return SearchDeploymentPlan(deployment.id, deployment.rollout_salt, deployment.state, bucket, SearchDeploymentVariant.LEXICAL.value, False, "approval_no_longer_active")
            if not assigned_to_canary(bucket=bucket, target_percent=deployment.target_percent):
                return SearchDeploymentPlan(deployment.id, deployment.rollout_salt, deployment.state, bucket, SearchDeploymentVariant.LEXICAL.value, True, "outside_canary_bucket")
            assigned = SearchDeploymentVariant.SHADOW.value if deployment.state == SearchDeploymentState.SHADOW.value else SearchDeploymentVariant.HYBRID.value
            return SearchDeploymentPlan(deployment.id, deployment.rollout_salt, deployment.state, bucket, assigned, True, None)

    async def record_observation(
        self,
        *,
        plan: SearchDeploymentPlan,
        subject_user_id: UUID,
        query_fingerprint: str,
        result_type: str,
        served_variant: str,
        duration_ms: float,
        success: bool,
        fallback_reason: str | None,
    ) -> UUID | None:
        if plan.deployment_id is None:
            return None
        observation_id = uuid7()
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            deployment = await session.get(SearchDeploymentModel, plan.deployment_id, with_for_update=True)
            if deployment is None:
                return None
            session.add(
                SearchDeploymentObservationModel(
                    id=observation_id,
                    deployment_id=deployment.id,
                    user_bucket=plan.bucket,
                    assigned_variant=plan.assigned_variant,
                    served_variant=served_variant,
                    query_fingerprint=query_fingerprint,
                    subject_fingerprint=_subject_fingerprint(subject_user_id, deployment.rollout_salt),
                    result_type=result_type,
                    duration_ms=max(0.0, duration_ms),
                    success=success,
                    fallback_reason=(fallback_reason or None),
                    created_at=now,
                )
            )
            if plan.assigned_variant in {SearchDeploymentVariant.HYBRID.value, SearchDeploymentVariant.SHADOW.value} and deployment.auto_pause:
                telemetry = await self._telemetry(session, deployment, now=now)
                breaker = self._breaker_from_telemetry(self._config_view(deployment), telemetry)
                active_state = (
                    SearchDeploymentState.CANARY.value
                    if plan.assigned_variant == SearchDeploymentVariant.HYBRID.value
                    else SearchDeploymentState.SHADOW.value
                )
                if breaker.should_pause and deployment.state == active_state:
                    previous_target = deployment.target_percent
                    deployment.state = SearchDeploymentState.PAUSED.value
                    deployment.target_percent = 0.0
                    deployment.updated_at = now
                    session.add(
                        SearchDeploymentActionModel(
                            id=uuid7(),
                            deployment_id=deployment.id,
                            action="auto_pause",
                            previous_state=active_state,
                            new_state=SearchDeploymentState.PAUSED.value,
                            target_percent=0.0,
                            rationale="; ".join(breaker.reasons),
                            metadata_={
                                "previous_target_percent": previous_target,
                                "sample_count": breaker.sample_count,
                                "error_rate": breaker.error_rate,
                                "p95_ms": breaker.p95_ms,
                                "assigned_variant": plan.assigned_variant,
                            },
                            actor_user_id=None,
                            created_at=now,
                        )
                    )
        return observation_id

    async def record_outcome(
        self,
        command: SearchDeploymentOutcomeCommand,
        *,
        subject_user_id: UUID,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            observation = await session.get(SearchDeploymentObservationModel, command.exposure_id)
            if observation is None:
                return False
            deployment = await session.get(SearchDeploymentModel, observation.deployment_id)
            if deployment is None:
                return False
            if observation.subject_fingerprint != _subject_fingerprint(subject_user_id, deployment.rollout_salt):
                return False
            existing = await session.scalar(
                select(SearchDeploymentOutcomeModel).where(
                    SearchDeploymentOutcomeModel.observation_id == observation.id,
                    SearchDeploymentOutcomeModel.action == command.action,
                    SearchDeploymentOutcomeModel.result_type == command.result_type,
                    SearchDeploymentOutcomeModel.result_id == command.result_id,
                )
            )
            if existing is not None:
                return True
            session.add(
                SearchDeploymentOutcomeModel(
                    id=uuid7(),
                    observation_id=observation.id,
                    action=command.action,
                    result_type=command.result_type,
                    result_id=command.result_id,
                    rank=command.rank,
                    created_at=datetime.now(UTC),
                )
            )
        return True

    async def _deployment(self, session: AsyncSession, *, for_update: bool = False) -> SearchDeploymentModel | None:
        statement = select(SearchDeploymentModel).where(SearchDeploymentModel.name == self.DEPLOYMENT_NAME)
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def _active_approved_evaluation(
        self,
        session: AsyncSession,
        decision_id: UUID,
    ) -> SearchPromotionEvaluationModel | None:
        decision = await session.get(SearchPromotionDecisionModel, decision_id)
        if decision is None or decision.decision != "approve_candidate":
            return None
        evaluation = await session.get(SearchPromotionEvaluationModel, decision.evaluation_id)
        if evaluation is None or evaluation.state != "pass":
            return None
        latest = await session.scalar(
            select(SearchPromotionDecisionModel)
            .where(SearchPromotionDecisionModel.evaluation_id == evaluation.id)
            .order_by(SearchPromotionDecisionModel.created_at.desc(), SearchPromotionDecisionModel.id.desc())
            .limit(1)
        )
        if latest is None or latest.id != decision.id or latest.decision != "approve_candidate":
            return None
        return evaluation

    async def _telemetry(
        self,
        session: AsyncSession,
        deployment: SearchDeploymentModel | None,
        *,
        now: datetime | None = None,
    ) -> SearchDeploymentTelemetryView:
        now = now or datetime.now(UTC)
        if deployment is None:
            return SearchDeploymentTelemetryView(
                window_minutes=15,
                sample_count=0,
                hybrid_assigned_count=0,
                hybrid_served_count=0,
                shadow_assigned_count=0,
                shadow_error_count=0,
                shadow_error_rate=None,
                shadow_p95_ms=None,
                fallback_count=0,
                hybrid_error_count=0,
                hybrid_error_rate=None,
                hybrid_p50_ms=None,
                hybrid_p95_ms=None,
                lexical_p50_ms=None,
                lexical_p95_ms=None,
                lexical_exposure_count=0,
                hybrid_exposure_count=0,
                lexical_open_exposure_count=0,
                hybrid_open_exposure_count=0,
                lexical_open_rate=None,
                hybrid_open_rate=None,
                open_outcome_count=0,
                generated_at=now,
            )
        since = now - timedelta(minutes=max(1, deployment.circuit_window_minutes))
        rows = list(
            (
                await session.execute(
                    select(SearchDeploymentObservationModel).where(
                        SearchDeploymentObservationModel.deployment_id == deployment.id,
                        SearchDeploymentObservationModel.created_at >= since,
                    )
                )
            ).scalars().all()
        )
        hybrid_assigned = [row for row in rows if row.assigned_variant == SearchDeploymentVariant.HYBRID.value]
        hybrid_served = [row for row in rows if row.served_variant == SearchDeploymentVariant.HYBRID.value]
        shadow_assigned = [row for row in rows if row.assigned_variant == SearchDeploymentVariant.SHADOW.value]
        lexical_served = [row for row in rows if row.served_variant == SearchDeploymentVariant.LEXICAL.value]
        fallback = [row for row in hybrid_assigned if row.served_variant != SearchDeploymentVariant.HYBRID.value]
        error_count = sum(1 for row in hybrid_assigned if not row.success)
        shadow_error_count = sum(1 for row in shadow_assigned if not row.success)
        outcome_count = 0
        opened_observation_ids: set[UUID] = set()
        if rows:
            obs_ids = [row.id for row in rows]
            outcome_rows = list(
                (
                    await session.execute(
                        select(SearchDeploymentOutcomeModel.observation_id).where(
                            SearchDeploymentOutcomeModel.observation_id.in_(obs_ids),
                            SearchDeploymentOutcomeModel.action == "open_result",
                        )
                    )
                ).scalars().all()
            )
            outcome_count = len(outcome_rows)
            opened_observation_ids = set(outcome_rows)
        lexical_open_exposures = sum(1 for row in lexical_served if row.id in opened_observation_ids)
        hybrid_open_exposures = sum(1 for row in hybrid_served if row.id in opened_observation_ids)
        return SearchDeploymentTelemetryView(
            window_minutes=deployment.circuit_window_minutes,
            sample_count=len(rows),
            hybrid_assigned_count=len(hybrid_assigned),
            hybrid_served_count=len(hybrid_served),
            shadow_assigned_count=len(shadow_assigned),
            shadow_error_count=shadow_error_count,
            shadow_error_rate=(shadow_error_count / len(shadow_assigned)) if shadow_assigned else None,
            shadow_p95_ms=_percentile([row.duration_ms for row in shadow_assigned], 0.95),
            fallback_count=len(fallback),
            hybrid_error_count=error_count,
            hybrid_error_rate=(error_count / len(hybrid_assigned)) if hybrid_assigned else None,
            hybrid_p50_ms=_percentile([row.duration_ms for row in hybrid_assigned], 0.50),
            hybrid_p95_ms=_percentile([row.duration_ms for row in hybrid_assigned], 0.95),
            lexical_p50_ms=_percentile([row.duration_ms for row in lexical_served], 0.50),
            lexical_p95_ms=_percentile([row.duration_ms for row in lexical_served], 0.95),
            lexical_exposure_count=len(lexical_served),
            hybrid_exposure_count=len(hybrid_served),
            lexical_open_exposure_count=lexical_open_exposures,
            hybrid_open_exposure_count=hybrid_open_exposures,
            lexical_open_rate=(lexical_open_exposures / len(lexical_served)) if lexical_served else None,
            hybrid_open_rate=(hybrid_open_exposures / len(hybrid_served)) if hybrid_served else None,
            open_outcome_count=outcome_count,
            generated_at=now,
        )

    def _breaker_from_telemetry(
        self,
        config: SearchDeploymentConfigView,
        telemetry: SearchDeploymentTelemetryView,
    ):
        use_shadow = config.state == SearchDeploymentState.SHADOW.value
        return assess_circuit_breaker_summary(
            sample_count=telemetry.shadow_assigned_count if use_shadow else telemetry.hybrid_assigned_count,
            error_count=telemetry.shadow_error_count if use_shadow else telemetry.hybrid_error_count,
            p95_ms=telemetry.shadow_p95_ms if use_shadow else telemetry.hybrid_p95_ms,
            policy=SearchCircuitBreakerPolicy(
                max_hybrid_p95_ms=config.max_hybrid_p95_ms,
                max_hybrid_error_rate=config.max_hybrid_error_rate,
                min_hybrid_samples=config.min_hybrid_samples,
            ),
        )

    async def _actions(
        self,
        session: AsyncSession,
        deployment: SearchDeploymentModel | None,
        *,
        limit: int,
    ) -> list[SearchDeploymentActionView]:
        if deployment is None:
            return []
        rows = list(
            (
                await session.execute(
                    select(SearchDeploymentActionModel)
                    .where(SearchDeploymentActionModel.deployment_id == deployment.id)
                    .order_by(SearchDeploymentActionModel.created_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            ).scalars().all()
        )
        return [
            SearchDeploymentActionView(
                id=row.id,
                action=row.action,
                previous_state=row.previous_state,
                new_state=row.new_state,
                target_percent=row.target_percent,
                rationale=row.rationale,
                metadata=dict(row.metadata_ or {}),
                actor_user_id=row.actor_user_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def _config_view(self, deployment: SearchDeploymentModel | None) -> SearchDeploymentConfigView:
        if deployment is None:
            return SearchDeploymentConfigView()
        return SearchDeploymentConfigView(
            id=deployment.id,
            name=deployment.name,
            state=deployment.state,
            target_percent=deployment.target_percent,
            promotion_decision_id=deployment.promotion_decision_id,
            benchmark_set=deployment.benchmark_set,
            max_hybrid_p95_ms=deployment.max_hybrid_p95_ms,
            max_hybrid_error_rate=deployment.max_hybrid_error_rate,
            min_hybrid_samples=deployment.min_hybrid_samples,
            circuit_window_minutes=deployment.circuit_window_minutes,
            auto_pause=deployment.auto_pause,
            updated_at=deployment.updated_at,
        )


class ProductionIntelligenceSearchService:
    """Production search facade with OFF-by-default, approval-gated semantic exposure."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        semantic_reranker: SemanticArticleReranker | None,
    ) -> None:
        self._lexical = IntelligenceSearchService(session_factory)
        self._deployment = SearchDeploymentControlService(session_factory)
        self._semantic_reranker = semantic_reranker

    async def search(
        self,
        *,
        subject_user_id: UUID,
        query: str,
        limit: int = 30,
        include_claims: bool = False,
        include_entities: bool = False,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
    ) -> IntelligenceSearchView:
        selected = (filters or SearchFilters()).normalized(include_claims=include_claims, include_entities=include_entities)
        plan = await self._deployment.plan(subject_user_id=subject_user_id, result_type=selected.result_type)
        started = perf_counter()
        lexical = await self._lexical.search(
            query=query,
            limit=limit,
            include_claims=include_claims,
            include_entities=include_entities,
            filters=selected,
            cursor=cursor,
        )
        response = lexical
        success = True
        fallback_reason: str | None = plan.reason
        served_variant = SearchDeploymentVariant.LEXICAL.value

        if plan.assigned_variant in {SearchDeploymentVariant.HYBRID.value, SearchDeploymentVariant.SHADOW.value}:
            if self._semantic_reranker is None:
                success = False
                fallback_reason = "semantic_reranker_unavailable"
            else:
                try:
                    hybrid = await self._semantic_reranker.rerank(
                        query=query,
                        lexical=lexical,
                        limit=limit,
                        preserve_cursor=True,
                        mode_label="hybrid_article_rerank_canary_v1",
                    )
                    if plan.assigned_variant == SearchDeploymentVariant.HYBRID.value:
                        response = hybrid
                        served_variant = SearchDeploymentVariant.HYBRID.value
                    else:
                        fallback_reason = "shadow_evaluation_served_lexical"
                except (SemanticRerankUnavailableError, ValueError) as exc:
                    success = False
                    fallback_reason = str(exc)[:240]

        duration_ms = max(0.0, (perf_counter() - started) * 1000.0)
        fingerprint = _search_fingerprint(query.strip(), selected, include_claims, include_entities)
        exposure_id = await self._deployment.record_observation(
            plan=plan,
            subject_user_id=subject_user_id,
            query_fingerprint=fingerprint,
            result_type=selected.result_type,
            served_variant=served_variant,
            duration_ms=duration_ms,
            success=success,
            fallback_reason=fallback_reason,
        )
        return response.model_copy(
            update={
                "deployment_variant": (
                    "hybrid_canary" if served_variant == SearchDeploymentVariant.HYBRID.value else
                    "shadow_lexical" if plan.assigned_variant == SearchDeploymentVariant.SHADOW.value else
                    "lexical"
                ),
                "deployment_exposure_id": exposure_id,
                "deployment_bucket": plan.bucket if plan.deployment_id is not None else None,
            }
        )


def _subject_fingerprint(subject_user_id: UUID, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{subject_user_id}".encode("utf-8")).hexdigest()[:32]


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1.0 - weight) + ordered[upper] * weight, 3)
