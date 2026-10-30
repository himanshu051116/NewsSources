from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean
from time import perf_counter
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from newsintel.application.search.dto import (
    SearchBenchmarkBundle,
    SearchBenchmarkBundleJudgment,
    SearchBenchmarkBundleQuery,
    SearchBenchmarkImportCommand,
    SearchBenchmarkImportView,
    SearchBenchmarkQueryCreateCommand,
    SearchBenchmarkQueryView,
    SearchBenchmarkRunCommand,
    SearchBenchmarkRunView,
    SearchBenchmarkComparisonView,
    SearchExperimentStatusView,
    SearchRelevanceJudgmentCommand,
    SearchRelevanceJudgmentView,
    SearchSlowDiagnosticsView,
    SearchSlowQueryGroupView,
    SearchTelemetryView,
    SearchSemanticCoverageView,
    SearchPromotionPolicyCommand,
    SearchPromotionPolicyView,
    SearchPromotionEvaluationView,
    SearchPromotionCheckView,
    SearchPromotionDecisionCommand,
    SearchPromotionDecisionView,
)
from newsintel.application.search.service import IntelligenceSearchService, SearchFilters
from newsintel.application.search.rerank_service import SemanticArticleReranker
from newsintel.core.ids import uuid7
from newsintel.domain.search.metrics import (
    aggregate_query_metrics,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from newsintel.domain.search.promotion import (
    SEARCH_PROMOTION_GATE_VERSION,
    SearchPromotionInput,
    SearchPromotionPolicy,
    SearchPromotionState,
    assess_search_promotion,
)
from newsintel.infrastructure.db.models import (
    SearchBenchmarkQueryModel,
    SearchBenchmarkRunModel,
    SearchQueryObservationModel,
    SearchRelevanceJudgmentModel,
    SearchPromotionPolicyModel,
    SearchPromotionEvaluationModel,
    SearchPromotionDecisionModel,
    ArticleVersionModel,
)


class SearchQualityService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        semantic_reranker: SemanticArticleReranker | None = None,
        semantic_collection: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._search = IntelligenceSearchService(session_factory)
        self._semantic_reranker = semantic_reranker
        self._semantic_collection = semantic_collection

    def experiment_status(self) -> SearchExperimentStatusView:
        return SearchExperimentStatusView(
            semantic_experiment_available=self._semantic_reranker is not None,
            embedding_model=self._semantic_reranker.model if self._semantic_reranker else None,
            qdrant_collection=self._semantic_collection if self._semantic_reranker else None,
        )

    async def create_query(
        self,
        command: SearchBenchmarkQueryCreateCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchBenchmarkQueryView:
        case_key = command.case_key or _case_key(command)
        filters = dict(command.filters)
        filters["result_type"] = command.result_type
        _filters_from_payload(filters).normalized(include_claims=True, include_entities=True)
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(SearchBenchmarkQueryModel).where(
                    SearchBenchmarkQueryModel.benchmark_set == command.benchmark_set,
                    SearchBenchmarkQueryModel.case_key == case_key,
                )
            )
            if existing is not None:
                return await self._query_view(session, existing)
            model = SearchBenchmarkQueryModel(
                id=uuid7(),
                benchmark_set=command.benchmark_set,
                case_key=case_key,
                query_text=command.query_text,
                result_type=command.result_type,
                filters=filters,
                language=command.language,
                topic_key=command.topic_key,
                notes=command.notes,
                created_by_user_id=actor_user_id,
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return await self._query_view(session, model)

    async def list_queries(self, benchmark_set: str) -> list[SearchBenchmarkQueryView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(SearchBenchmarkQueryModel)
                        .where(SearchBenchmarkQueryModel.benchmark_set == benchmark_set)
                        .order_by(SearchBenchmarkQueryModel.created_at.asc())
                    )
                ).all()
            )
            return [await self._query_view(session, item) for item in rows]

    async def upsert_judgment(
        self,
        query_id: UUID,
        command: SearchRelevanceJudgmentCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchRelevanceJudgmentView | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            if await session.get(SearchBenchmarkQueryModel, query_id) is None:
                return None
            model = await session.scalar(
                select(SearchRelevanceJudgmentModel).where(
                    SearchRelevanceJudgmentModel.query_id == query_id,
                    SearchRelevanceJudgmentModel.result_type == command.result_type,
                    SearchRelevanceJudgmentModel.result_id == command.result_id,
                )
            )
            if model is None:
                model = SearchRelevanceJudgmentModel(
                    id=uuid7(),
                    query_id=query_id,
                    result_type=command.result_type,
                    result_id=command.result_id,
                    relevance_grade=command.relevance_grade,
                    rationale=command.rationale,
                    adjudicator_user_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
            else:
                model.relevance_grade = command.relevance_grade
                model.rationale = command.rationale
                model.adjudicator_user_id = actor_user_id
                model.updated_at = now
            await session.flush()
            return _judgment_view(model)

    async def list_judgments(self, query_id: UUID) -> list[SearchRelevanceJudgmentView] | None:
        async with self._session_factory() as session:
            if await session.get(SearchBenchmarkQueryModel, query_id) is None:
                return None
            rows = list(
                (
                    await session.scalars(
                        select(SearchRelevanceJudgmentModel)
                        .where(SearchRelevanceJudgmentModel.query_id == query_id)
                        .order_by(SearchRelevanceJudgmentModel.relevance_grade.desc(), SearchRelevanceJudgmentModel.updated_at.desc())
                    )
                ).all()
            )
            return [_judgment_view(item) for item in rows]

    async def evaluate(
        self,
        benchmark_set: str,
        command: SearchBenchmarkRunCommand,
    ) -> SearchBenchmarkRunView:
        k_values = sorted({int(k) for k in command.k_values if 1 <= int(k) <= command.max_results})
        if not k_values:
            raise ValueError("at least one k value must be between 1 and max_results")
        async with self._session_factory() as session:
            queries = list(
                (
                    await session.scalars(
                        select(SearchBenchmarkQueryModel)
                        .where(SearchBenchmarkQueryModel.benchmark_set == benchmark_set)
                        .order_by(SearchBenchmarkQueryModel.created_at.asc())
                    )
                ).all()
            )
            if not queries:
                raise ValueError(f"no search benchmark queries found for set: {benchmark_set}")
            if command.search_mode == "hybrid_article_rerank":
                if self._semantic_reranker is None:
                    raise ValueError(
                        "semantic reranking experiment is unavailable; enable the local semantic index and AI provider first"
                    )
                non_article = [item for item in queries if item.result_type != "article"]
                if non_article:
                    raise ValueError(
                        "hybrid reranking benchmarks must contain article-only queries so lexical and semantic ordering remain comparable"
                    )
            query_ids = [item.id for item in queries]
            judgments = list(
                (
                    await session.scalars(
                        select(SearchRelevanceJudgmentModel).where(
                            SearchRelevanceJudgmentModel.query_id.in_(query_ids)
                        )
                    )
                ).all()
            )
        judgments_by_query: dict[UUID, dict[tuple[str, str], int]] = {}
        for item in judgments:
            judgments_by_query.setdefault(item.query_id, {})[(item.result_type, str(item.result_id))] = int(item.relevance_grade)
        benchmark_fingerprint = _search_benchmark_fingerprint(queries, judgments_by_query)

        per_query_metrics: list[dict[str, float | None]] = []
        metric_rows: list[tuple[SearchBenchmarkQueryModel, dict[str, float | None], bool, bool]] = []
        latencies: list[float] = []
        judged_query_count = 0
        relevant_query_count = 0
        allowed_slices = {"language", "topic_key", "result_type"}
        requested_slices = []
        for dimension in command.slice_by:
            if dimension not in allowed_slices:
                raise ValueError(f"unsupported benchmark slice: {dimension}")
            if dimension not in requested_slices:
                requested_slices.append(dimension)
        for query in queries:
            grades = judgments_by_query.get(query.id, {})
            judged = bool(grades)
            relevant = any(grade > 0 for grade in grades.values())
            if judged:
                judged_query_count += 1
            if relevant:
                relevant_query_count += 1
            filters = _filters_from_payload(dict(query.filters or {}))
            started = perf_counter()
            candidate_limit = (
                min(100, max(command.max_results, command.max_results * 3))
                if command.search_mode == "hybrid_article_rerank"
                else command.max_results
            )
            result = await self._search.search(
                query=query.query_text,
                limit=candidate_limit,
                include_claims=True,
                include_entities=True,
                filters=filters,
                record_telemetry=False,
            )
            if command.search_mode == "hybrid_article_rerank":
                assert self._semantic_reranker is not None
                result = await self._semantic_reranker.rerank(
                    query=query.query_text,
                    lexical=result,
                    limit=command.max_results,
                )
            latencies.append(max(0.0, (perf_counter() - started) * 1000.0))
            ranked = [(item.result_type, str(item.id)) for item in result.results[: command.max_results]]
            metrics: dict[str, float | None] = {"mrr": reciprocal_rank(ranked, grades)}
            for k in k_values:
                metrics[f"precision@{k}"] = precision_at_k(ranked, grades, k)
                metrics[f"recall@{k}"] = recall_at_k(ranked, grades, k)
                metrics[f"ndcg@{k}"] = ndcg_at_k(ranked, grades, k)
            per_query_metrics.append(metrics)
            metric_rows.append((query, metrics, judged, relevant))

        aggregate: dict[str, object] = aggregate_query_metrics(per_query_metrics)
        aggregate["judgment_coverage"] = round(judged_query_count / len(queries), 6)
        aggregate["relevant_query_coverage"] = round(relevant_query_count / len(queries), 6)
        aggregate["slices"] = _slice_aggregates(metric_rows, requested_slices)
        latency = _latency_payload(latencies)
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            model = SearchBenchmarkRunModel(
                id=uuid7(),
                benchmark_set=benchmark_set,
                search_mode=("hybrid_article_rerank_v1" if command.search_mode == "hybrid_article_rerank" else "postgres_fts_v3_multilingual"),
                query_count=len(queries),
                judged_query_count=judged_query_count,
                metrics={
                    **aggregate,
                    "k_values": k_values,
                    "queries_with_relevant_judgments": relevant_query_count,
                },
                latency=latency,
                metadata_={
                    "max_results": command.max_results,
                    "requested_search_mode": command.search_mode,
                    "semantic_model": self._semantic_reranker.model if command.search_mode == "hybrid_article_rerank" and self._semantic_reranker else None,
                    "candidate_pool_size": (min(100, max(command.max_results, command.max_results * 3)) if command.search_mode == "hybrid_article_rerank" else command.max_results),
                    "benchmark_fingerprint": benchmark_fingerprint,
                    "interpretation": (
                        "Unjudged returned results are treated as non-relevant for ranking metrics. "
                        "Benchmark conclusions should therefore be made only after adequate judgment coverage."
                    ),
                },
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _run_view(model)

    async def compare_latest_modes(self, benchmark_set: str) -> SearchBenchmarkComparisonView:
        lexical, hybrid = await self._latest_comparable_runs(benchmark_set)
        if lexical is None or hybrid is None:
            return SearchBenchmarkComparisonView(
                benchmark_set=benchmark_set,
                available=False,
                lexical_run_id=lexical.id if lexical else None,
                hybrid_run_id=hybrid.id if hybrid else None,
                lexical_judged_query_count=lexical.judged_query_count if lexical else None,
                hybrid_judged_query_count=hybrid.judged_query_count if hybrid else None,
                note="Run both the production lexical baseline and the hybrid article reranking experiment on the same labelled benchmark before comparing them.",
            )
        lexical_fingerprint = str((lexical.metadata_ or {}).get("benchmark_fingerprint") or "")
        hybrid_fingerprint = str((hybrid.metadata_ or {}).get("benchmark_fingerprint") or "")
        if not lexical_fingerprint or lexical_fingerprint != hybrid_fingerprint:
            return SearchBenchmarkComparisonView(
                benchmark_set=benchmark_set,
                available=False,
                lexical_run_id=lexical.id,
                hybrid_run_id=hybrid.id,
                lexical_judged_query_count=lexical.judged_query_count,
                hybrid_judged_query_count=hybrid.judged_query_count,
                note=(
                    "No comparable lexical/hybrid pair shares the exact same query/judgment snapshot. "
                    "Re-run both modes after the benchmark is frozen before interpreting deltas."
                ),
            )
        metric_keys = ["mrr", "precision@10", "recall@10", "ndcg@10", "judgment_coverage"]
        metric_deltas = {
            key: _numeric_delta(hybrid.metrics.get(key), lexical.metrics.get(key))
            for key in metric_keys
        }
        latency_deltas = {
            key: _numeric_delta(hybrid.latency.get(key), lexical.latency.get(key))
            for key in ("p50_ms", "p95_ms", "mean_ms", "max_ms")
        }
        return SearchBenchmarkComparisonView(
            benchmark_set=benchmark_set,
            available=True,
            lexical_run_id=lexical.id,
            hybrid_run_id=hybrid.id,
            metric_deltas=metric_deltas,
            latency_deltas_ms=latency_deltas,
            lexical_judged_query_count=lexical.judged_query_count,
            hybrid_judged_query_count=hybrid.judged_query_count,
            note=(
                "Positive ranking deltas favor the hybrid experiment; positive latency deltas mean it is slower. "
                "The newest comparable frozen-benchmark pair is used. No mode is promoted automatically."
            ),
        )

    async def history(self, benchmark_set: str, *, limit: int = 50) -> list[SearchBenchmarkRunView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(SearchBenchmarkRunModel)
                        .where(SearchBenchmarkRunModel.benchmark_set == benchmark_set)
                        .order_by(SearchBenchmarkRunModel.created_at.desc())
                        .limit(max(1, min(limit, 200)))
                    )
                ).all()
            )
        return [_run_view(item) for item in rows]

    async def telemetry(self, *, window_hours: int = 24) -> SearchTelemetryView:
        if window_hours < 1 or window_hours > 24 * 30:
            raise ValueError("window_hours must be between 1 and 720")
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        async with self._session_factory() as session:
            values = list(
                (
                    await session.execute(
                        select(
                            SearchQueryObservationModel.duration_ms,
                            SearchQueryObservationModel.returned_count,
                            SearchQueryObservationModel.cursor_page,
                        ).where(SearchQueryObservationModel.created_at >= cutoff)
                    )
                ).all()
            )
        durations = sorted(float(row.duration_ms) for row in values)
        returned = [int(row.returned_count) for row in values]
        return SearchTelemetryView(
            window_hours=window_hours,
            observation_count=len(values),
            first_page_count=sum(1 for row in values if not bool(row.cursor_page)),
            cursor_page_count=sum(1 for row in values if bool(row.cursor_page)),
            p50_ms=_percentile(durations, 0.50),
            p95_ms=_percentile(durations, 0.95),
            max_ms=max(durations) if durations else None,
            mean_ms=round(mean(durations), 3) if durations else None,
            slow_over_1500_ms=sum(1 for value in durations if value > 1500.0),
            mean_returned_count=round(mean(returned), 3) if returned else None,
            generated_at=datetime.now(UTC),
        )

    async def semantic_coverage(self) -> SearchSemanticCoverageView:
        now = datetime.now(UTC)
        newer = aliased(ArticleVersionModel)
        current_condition = ~exists(
            select(1).where(
                newer.article_id == ArticleVersionModel.article_id,
                newer.version_number > ArticleVersionModel.version_number,
                newer.created_at <= now,
            )
        )
        expected_model = self._semantic_reranker.model if self._semantic_reranker else None
        fresh_conditions = [
            ArticleVersionModel.semantic_indexed_at.is_not(None),
            ArticleVersionModel.semantic_content_sha256 == ArticleVersionModel.content_sha256,
        ]
        if expected_model:
            fresh_conditions.append(ArticleVersionModel.semantic_model == expected_model)
        stale_condition = or_(
            ArticleVersionModel.semantic_content_sha256.is_(None),
            ArticleVersionModel.semantic_content_sha256 != ArticleVersionModel.content_sha256,
        )
        if expected_model:
            stale_condition = or_(stale_condition, ArticleVersionModel.semantic_model.is_(None), ArticleVersionModel.semantic_model != expected_model)
        async with self._session_factory() as session:
            total = int(
                await session.scalar(
                    select(func.count(ArticleVersionModel.id)).where(
                        ArticleVersionModel.created_at <= now,
                        current_condition,
                    )
                )
                or 0
            )
            indexed = int(
                await session.scalar(
                    select(func.count(ArticleVersionModel.id)).where(
                        ArticleVersionModel.created_at <= now,
                        current_condition,
                        ArticleVersionModel.semantic_indexed_at.is_not(None),
                    )
                )
                or 0
            )
            fresh = int(
                await session.scalar(
                    select(func.count(ArticleVersionModel.id)).where(
                        ArticleVersionModel.created_at <= now,
                        current_condition,
                        *fresh_conditions,
                    )
                )
                or 0
            )
            stale = int(
                await session.scalar(
                    select(func.count(ArticleVersionModel.id)).where(
                        ArticleVersionModel.created_at <= now,
                        current_condition,
                        ArticleVersionModel.semantic_indexed_at.is_not(None),
                        stale_condition,
                    )
                )
                or 0
            )
        return SearchSemanticCoverageView(
            current_article_versions=total,
            indexed_article_versions=indexed,
            fresh_article_versions=fresh,
            missing_article_versions=max(0, total - indexed),
            stale_article_versions=stale,
            expected_model=expected_model,
            fresh_coverage=round(fresh / total, 6) if total else None,
            indexed_coverage=round(indexed / total, 6) if total else None,
            generated_at=now,
        )

    async def promotion_policy(self, benchmark_set: str) -> SearchPromotionPolicyView:
        async with self._session_factory() as session:
            model = await session.scalar(
                select(SearchPromotionPolicyModel).where(SearchPromotionPolicyModel.benchmark_set == benchmark_set)
            )
        if model is None:
            return _default_promotion_policy_view(benchmark_set)
        return _promotion_policy_view(model)

    async def save_promotion_policy(
        self,
        benchmark_set: str,
        command: SearchPromotionPolicyCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchPromotionPolicyView:
        now = datetime.now(UTC)
        thresholds = _promotion_thresholds_from_command(command)
        async with self._session_factory() as session, session.begin():
            model = await session.scalar(
                select(SearchPromotionPolicyModel).where(SearchPromotionPolicyModel.benchmark_set == benchmark_set)
            )
            if model is None:
                model = SearchPromotionPolicyModel(
                    id=uuid7(),
                    benchmark_set=benchmark_set,
                    name=command.name,
                    thresholds=thresholds,
                    required_languages=_clean_string_list(command.required_languages),
                    required_topics=_clean_string_list(command.required_topics),
                    created_by_user_id=actor_user_id,
                    updated_by_user_id=actor_user_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
            else:
                model.name = command.name
                model.thresholds = thresholds
                model.required_languages = _clean_string_list(command.required_languages)
                model.required_topics = _clean_string_list(command.required_topics)
                model.updated_by_user_id = actor_user_id
                model.updated_at = now
            await session.flush()
            return _promotion_policy_view(model)

    async def evaluate_promotion_gate(
        self,
        benchmark_set: str,
        *,
        actor_user_id: UUID | None,
    ) -> SearchPromotionEvaluationView:
        policy_view = await self.promotion_policy(benchmark_set)
        if not policy_view.persisted:
            policy_view = await self.save_promotion_policy(
                benchmark_set,
                SearchPromotionPolicyCommand(**policy_view.model_dump(exclude={"id", "benchmark_set", "persisted", "created_at", "updated_at"})),
                actor_user_id=actor_user_id,
            )
        assert policy_view.id is not None
        coverage = await self.semantic_coverage()
        lexical, hybrid = await self._latest_comparable_runs(benchmark_set)
        now = datetime.now(UTC)
        if lexical is None or hybrid is None:
            return await self._persist_blocked_promotion_evaluation(
                policy_view,
                benchmark_set,
                lexical,
                hybrid,
                coverage,
                actor_user_id=actor_user_id,
                message="Comparable lexical and hybrid benchmark runs with the same frozen benchmark fingerprint are required.",
                now=now,
            )
        lexical_fingerprint = str((lexical.metadata_ or {}).get("benchmark_fingerprint") or "")
        hybrid_fingerprint = str((hybrid.metadata_ or {}).get("benchmark_fingerprint") or "")
        if not lexical_fingerprint or lexical_fingerprint != hybrid_fingerprint:
            return await self._persist_blocked_promotion_evaluation(
                policy_view,
                benchmark_set,
                lexical,
                hybrid,
                coverage,
                actor_user_id=actor_user_id,
                message="The selected lexical and hybrid runs do not share the exact same benchmark fingerprint.",
                now=now,
            )
        policy = _promotion_policy_domain(policy_view)
        input_metrics = SearchPromotionInput(
            query_count=min(lexical.query_count, hybrid.query_count),
            judged_query_count=min(lexical.judged_query_count, hybrid.judged_query_count),
            judgment_coverage=_min_numeric(lexical.metrics.get("judgment_coverage"), hybrid.metrics.get("judgment_coverage")),
            relevant_query_coverage=_min_numeric(lexical.metrics.get("relevant_query_coverage"), hybrid.metrics.get("relevant_query_coverage")),
            ndcg_delta=_numeric_delta(hybrid.metrics.get("ndcg@10"), lexical.metrics.get("ndcg@10")),
            mrr_delta=_numeric_delta(hybrid.metrics.get("mrr"), lexical.metrics.get("mrr")),
            recall_delta=_numeric_delta(hybrid.metrics.get("recall@10"), lexical.metrics.get("recall@10")),
            lexical_p95_ms=_numeric(lexical.latency.get("p95_ms")),
            hybrid_p95_ms=_numeric(hybrid.latency.get("p95_ms")),
            semantic_coverage=coverage.fresh_coverage,
            lexical_slices=dict(lexical.metrics.get("slices") or {}),
            hybrid_slices=dict(hybrid.metrics.get("slices") or {}),
        )
        assessment = assess_search_promotion(input_metrics, policy)
        checks = [
            {
                "key": item.key,
                "state": item.state.value,
                "actual": item.actual,
                "threshold": item.threshold,
                "message": item.message,
            }
            for item in assessment.checks
        ]
        async with self._session_factory() as session, session.begin():
            model = SearchPromotionEvaluationModel(
                id=uuid7(),
                policy_id=policy_view.id,
                benchmark_set=benchmark_set,
                lexical_run_id=lexical.id,
                hybrid_run_id=hybrid.id,
                benchmark_fingerprint=lexical_fingerprint,
                state=assessment.state.value,
                checks=checks,
                failures=list(assessment.failures),
                warnings=list(assessment.warnings),
                semantic_coverage=coverage.model_dump(mode="json"),
                methodology_version=assessment.methodology_version,
                interpretation=assessment.interpretation,
                evaluated_by_user_id=actor_user_id,
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _promotion_evaluation_view(model)

    async def record_promotion_decision(
        self,
        evaluation_id: UUID,
        command: SearchPromotionDecisionCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchPromotionDecisionView | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            evaluation = await session.get(SearchPromotionEvaluationModel, evaluation_id)
            if evaluation is None:
                return None
            if command.decision == "approve_candidate" and evaluation.state != SearchPromotionState.PASS.value:
                raise ValueError("only a PASS gate evaluation can be approved as a release candidate")
            model = SearchPromotionDecisionModel(
                id=uuid7(),
                evaluation_id=evaluation.id,
                decision=command.decision,
                rationale=command.rationale,
                decided_by_user_id=actor_user_id,
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return SearchPromotionDecisionView(
                id=model.id,
                evaluation_id=model.evaluation_id,
                benchmark_set=evaluation.benchmark_set,
                gate_state=evaluation.state,
                decision=model.decision,
                rationale=model.rationale,
                decided_by_user_id=model.decided_by_user_id,
                created_at=model.created_at,
            )

    async def promotion_decisions(
        self,
        benchmark_set: str,
        *,
        limit: int = 30,
    ) -> list[SearchPromotionDecisionView]:
        statement = (
            select(SearchPromotionDecisionModel, SearchPromotionEvaluationModel)
            .join(
                SearchPromotionEvaluationModel,
                SearchPromotionEvaluationModel.id == SearchPromotionDecisionModel.evaluation_id,
            )
            .where(SearchPromotionEvaluationModel.benchmark_set == benchmark_set)
            .order_by(SearchPromotionDecisionModel.created_at.desc())
            .limit(max(1, min(limit, 100)))
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).all())
        return [
            SearchPromotionDecisionView(
                id=decision.id,
                evaluation_id=decision.evaluation_id,
                benchmark_set=evaluation.benchmark_set,
                gate_state=evaluation.state,
                decision=decision.decision,
                rationale=decision.rationale,
                decided_by_user_id=decision.decided_by_user_id,
                created_at=decision.created_at,
            )
            for decision, evaluation in rows
        ]

    async def promotion_history(self, benchmark_set: str, *, limit: int = 30) -> list[SearchPromotionEvaluationView]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(SearchPromotionEvaluationModel)
                        .where(SearchPromotionEvaluationModel.benchmark_set == benchmark_set)
                        .order_by(SearchPromotionEvaluationModel.created_at.desc())
                        .limit(max(1, min(limit, 100)))
                    )
                ).all()
            )
        return [_promotion_evaluation_view(item) for item in rows]

    async def _latest_comparable_runs(
        self,
        benchmark_set: str,
    ) -> tuple[SearchBenchmarkRunModel | None, SearchBenchmarkRunModel | None]:
        async with self._session_factory() as session:
            rows = list(
                (
                    await session.scalars(
                        select(SearchBenchmarkRunModel)
                        .where(
                            SearchBenchmarkRunModel.benchmark_set == benchmark_set,
                            SearchBenchmarkRunModel.search_mode.in_(["postgres_fts_v3_multilingual", "hybrid_article_rerank_v1"]),
                        )
                        .order_by(SearchBenchmarkRunModel.created_at.desc())
                        .limit(200)
                    )
                ).all()
            )
        lexical_by_fingerprint: dict[str, SearchBenchmarkRunModel] = {}
        hybrid_by_fingerprint: dict[str, SearchBenchmarkRunModel] = {}
        for item in rows:
            fingerprint = str((item.metadata_ or {}).get("benchmark_fingerprint") or "")
            if not fingerprint:
                continue
            if item.search_mode == "postgres_fts_v3_multilingual":
                lexical_by_fingerprint.setdefault(fingerprint, item)
            elif item.search_mode == "hybrid_article_rerank_v1":
                hybrid_by_fingerprint.setdefault(fingerprint, item)
        common = set(lexical_by_fingerprint).intersection(hybrid_by_fingerprint)
        if not common:
            return (
                next(iter(lexical_by_fingerprint.values()), None),
                next(iter(hybrid_by_fingerprint.values()), None),
            )
        fingerprint = max(
            common,
            key=lambda value: max(
                lexical_by_fingerprint[value].created_at,
                hybrid_by_fingerprint[value].created_at,
            ),
        )
        return lexical_by_fingerprint[fingerprint], hybrid_by_fingerprint[fingerprint]

    async def _persist_blocked_promotion_evaluation(
        self,
        policy: SearchPromotionPolicyView,
        benchmark_set: str,
        lexical: SearchBenchmarkRunModel | None,
        hybrid: SearchBenchmarkRunModel | None,
        coverage: SearchSemanticCoverageView,
        *,
        actor_user_id: UUID | None,
        message: str,
        now: datetime,
    ) -> SearchPromotionEvaluationView:
        assert policy.id is not None
        fingerprints = {
            str((item.metadata_ or {}).get("benchmark_fingerprint") or "")
            for item in (lexical, hybrid)
            if item is not None
        }
        fingerprint = next(iter(fingerprints)) if len(fingerprints) == 1 else None
        async with self._session_factory() as session, session.begin():
            model = SearchPromotionEvaluationModel(
                id=uuid7(),
                policy_id=policy.id,
                benchmark_set=benchmark_set,
                lexical_run_id=lexical.id if lexical else None,
                hybrid_run_id=hybrid.id if hybrid else None,
                benchmark_fingerprint=fingerprint,
                state=SearchPromotionState.BLOCKED.value,
                checks=[{"key": "comparable_runs", "state": "blocked", "actual": None, "threshold": "matching frozen benchmark", "message": message}],
                failures=[message],
                warnings=[],
                semantic_coverage=coverage.model_dump(mode="json"),
                methodology_version=SEARCH_PROMOTION_GATE_VERSION,
                interpretation="Promotion evaluation is blocked until like-for-like benchmark runs are available. No production search mode is changed.",
                evaluated_by_user_id=actor_user_id,
                created_at=now,
            )
            session.add(model)
            await session.flush()
            return _promotion_evaluation_view(model)

    async def export_bundle(self, benchmark_set: str) -> SearchBenchmarkBundle:
        async with self._session_factory() as session:
            queries = list((await session.scalars(select(SearchBenchmarkQueryModel).where(
                SearchBenchmarkQueryModel.benchmark_set == benchmark_set
            ).order_by(SearchBenchmarkQueryModel.created_at.asc()))).all())
            if not queries:
                raise ValueError(f"no search benchmark queries found for set: {benchmark_set}")
            query_ids = [item.id for item in queries]
            judgments = list((await session.scalars(select(SearchRelevanceJudgmentModel).where(
                SearchRelevanceJudgmentModel.query_id.in_(query_ids)
            ).order_by(SearchRelevanceJudgmentModel.created_at.asc()))).all())
        by_query: dict[UUID, list[SearchRelevanceJudgmentModel]] = defaultdict(list)
        for item in judgments:
            by_query[item.query_id].append(item)
        return SearchBenchmarkBundle(
            benchmark_set=benchmark_set,
            exported_at=datetime.now(UTC),
            queries=[
                SearchBenchmarkBundleQuery(
                    query_text=item.query_text,
                    result_type=item.result_type,
                    filters=dict(item.filters or {}),
                    language=item.language,
                    topic_key=item.topic_key,
                    notes=item.notes,
                    case_key=item.case_key,
                    judgments=[
                        SearchBenchmarkBundleJudgment(
                            result_type=j.result_type,
                            result_id=j.result_id,
                            relevance_grade=j.relevance_grade,
                            rationale=j.rationale,
                        )
                        for j in by_query.get(item.id, [])
                    ],
                )
                for item in queries
            ],
        )

    async def import_bundle(
        self,
        command: SearchBenchmarkImportCommand,
        *,
        actor_user_id: UUID | None,
    ) -> SearchBenchmarkImportView:
        existing = {item.case_key for item in await self.list_queries(command.benchmark_set)}
        judgment_count = 0
        existing_count = 0
        for item in command.queries:
            create = SearchBenchmarkQueryCreateCommand(
                benchmark_set=command.benchmark_set,
                query_text=item.query_text,
                result_type=item.result_type,
                filters=item.filters,
                language=item.language,
                topic_key=item.topic_key,
                notes=item.notes,
                case_key=item.case_key,
            )
            case_key = create.case_key or _case_key(create)
            if case_key in existing:
                existing_count += 1
            view = await self.create_query(create, actor_user_id=actor_user_id)
            existing.add(view.case_key)
            for judgment in item.judgments:
                await self.upsert_judgment(
                    view.id,
                    SearchRelevanceJudgmentCommand(
                        result_type=judgment.result_type,
                        result_id=judgment.result_id,
                        relevance_grade=judgment.relevance_grade,
                        rationale=judgment.rationale,
                    ),
                    actor_user_id=actor_user_id,
                )
                judgment_count += 1
        return SearchBenchmarkImportView(
            benchmark_set=command.benchmark_set,
            query_count=len(command.queries),
            judgment_count=judgment_count,
            existing_query_count=existing_count,
        )

    async def slow_diagnostics(
        self,
        *,
        window_hours: int = 24,
        threshold_ms: float = 750.0,
        limit: int = 30,
    ) -> SearchSlowDiagnosticsView:
        if window_hours < 1 or window_hours > 720:
            raise ValueError("window_hours must be between 1 and 720")
        if threshold_ms < 1 or threshold_ms > 120_000:
            raise ValueError("threshold_ms must be between 1 and 120000")
        cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
        async with self._session_factory() as session:
            rows = list((await session.scalars(select(SearchQueryObservationModel).where(
                SearchQueryObservationModel.created_at >= cutoff,
                SearchQueryObservationModel.duration_ms >= threshold_ms,
            ).order_by(SearchQueryObservationModel.duration_ms.desc()).limit(20_000))).all())
        grouped: dict[tuple[str, str, str], list[SearchQueryObservationModel]] = defaultdict(list)
        for row in rows:
            filter_key = json.dumps(dict(row.filters or {}), sort_keys=True, separators=(",", ":"))
            grouped[(row.query_fingerprint, row.result_type, filter_key)].append(row)
        views: list[SearchSlowQueryGroupView] = []
        for (fingerprint, result_type, filter_key), items in grouped.items():
            durations = sorted(float(item.duration_ms) for item in items)
            filters = json.loads(filter_key)
            views.append(
                SearchSlowQueryGroupView(
                    query_fingerprint=fingerprint,
                    result_type=result_type,
                    filters=filters,
                    observation_count=len(items),
                    p50_ms=float(_percentile(durations, 0.50) or 0.0),
                    p95_ms=float(_percentile(durations, 0.95) or 0.0),
                    max_ms=round(max(durations), 3),
                    mean_ms=round(mean(durations), 3),
                    cursor_page_ratio=round(sum(1 for item in items if item.cursor_page) / len(items), 6),
                    mean_result_count=round(mean(int(item.result_count) for item in items), 3),
                    mean_returned_count=round(mean(int(item.returned_count) for item in items), 3),
                    diagnosis=_slow_diagnosis(result_type, filters, items),
                )
            )
        views.sort(key=lambda item: (-item.p95_ms, -item.observation_count, item.query_fingerprint))
        return SearchSlowDiagnosticsView(
            window_hours=window_hours,
            threshold_ms=threshold_ms,
            group_count=len(views),
            groups=views[: max(1, min(limit, 100))],
            generated_at=datetime.now(UTC),
        )

    async def _query_view(self, session: AsyncSession, model: SearchBenchmarkQueryModel) -> SearchBenchmarkQueryView:
        counts = (
            await session.execute(
                select(
                    func.count(SearchRelevanceJudgmentModel.id),
                    func.count(SearchRelevanceJudgmentModel.id).filter(SearchRelevanceJudgmentModel.relevance_grade > 0),
                ).where(SearchRelevanceJudgmentModel.query_id == model.id)
            )
        ).one()
        return SearchBenchmarkQueryView(
            id=model.id,
            benchmark_set=model.benchmark_set,
            case_key=model.case_key,
            query_text=model.query_text,
            result_type=model.result_type,
            filters=dict(model.filters or {}),
            language=model.language,
            topic_key=model.topic_key,
            notes=model.notes,
            judgment_count=int(counts[0] or 0),
            relevant_judgment_count=int(counts[1] or 0),
            created_at=model.created_at,
        )


def _case_key(command: SearchBenchmarkQueryCreateCommand) -> str:
    payload = {
        "query": command.query_text,
        "result_type": command.result_type,
        "filters": command.filters,
        "language": command.language,
        "topic_key": command.topic_key,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _filters_from_payload(payload: dict[str, object]) -> SearchFilters:
    return SearchFilters(
        result_type=str(payload.get("result_type") or "all"),
        language=_optional_str(payload.get("language")),
        publisher=_optional_str(payload.get("publisher")),
        lifecycle_status=_optional_str(payload.get("lifecycle_status")),
        from_date=_optional_datetime(payload.get("from_date")),
        to_date=_optional_datetime(payload.get("to_date")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_datetime(value: object) -> datetime | None:
    text = _optional_str(value)
    if text is None:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _judgment_view(item: SearchRelevanceJudgmentModel) -> SearchRelevanceJudgmentView:
    return SearchRelevanceJudgmentView(
        id=item.id,
        query_id=item.query_id,
        result_type=item.result_type,
        result_id=item.result_id,
        relevance_grade=item.relevance_grade,
        rationale=item.rationale,
        adjudicator_user_id=item.adjudicator_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _search_benchmark_fingerprint(
    queries: list[SearchBenchmarkQueryModel],
    judgments_by_query: dict[UUID, dict[tuple[str, str], int]],
) -> str:
    payload = []
    for query in sorted(queries, key=lambda item: str(item.id)):
        grades = judgments_by_query.get(query.id, {})
        payload.append(
            {
                "id": str(query.id),
                "case_key": query.case_key,
                "query_text": query.query_text,
                "result_type": query.result_type,
                "filters": dict(query.filters or {}),
                "language": query.language,
                "topic_key": query.topic_key,
                "judgments": [
                    [kind, result_id, grade]
                    for (kind, result_id), grade in sorted(grades.items())
                ],
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()



def _clean_string_list(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _promotion_thresholds_from_command(command: SearchPromotionPolicyCommand) -> dict[str, object]:
    return {
        "min_query_count": command.min_query_count,
        "min_judgment_coverage": command.min_judgment_coverage,
        "min_relevant_query_coverage": command.min_relevant_query_coverage,
        "min_ndcg_delta": command.min_ndcg_delta,
        "min_mrr_delta": command.min_mrr_delta,
        "min_recall_delta": command.min_recall_delta,
        "max_hybrid_p95_ms": command.max_hybrid_p95_ms,
        "max_p95_regression_ms": command.max_p95_regression_ms,
        "min_semantic_coverage": command.min_semantic_coverage,
        "min_slice_judged_queries": command.min_slice_judged_queries,
        "max_slice_ndcg_drop": command.max_slice_ndcg_drop,
    }


def _default_promotion_policy_view(benchmark_set: str) -> SearchPromotionPolicyView:
    command = SearchPromotionPolicyCommand()
    return SearchPromotionPolicyView(
        benchmark_set=benchmark_set,
        persisted=False,
        **command.model_dump(),
    )


def _promotion_policy_view(model: SearchPromotionPolicyModel) -> SearchPromotionPolicyView:
    defaults = SearchPromotionPolicyCommand().model_dump()
    defaults.update(dict(model.thresholds or {}))
    defaults["name"] = model.name
    defaults["required_languages"] = list(model.required_languages or [])
    defaults["required_topics"] = list(model.required_topics or [])
    return SearchPromotionPolicyView(
        id=model.id,
        benchmark_set=model.benchmark_set,
        persisted=True,
        created_at=model.created_at,
        updated_at=model.updated_at,
        **defaults,
    )


def _promotion_policy_domain(view: SearchPromotionPolicyView) -> SearchPromotionPolicy:
    return SearchPromotionPolicy(
        min_query_count=view.min_query_count,
        min_judgment_coverage=view.min_judgment_coverage,
        min_relevant_query_coverage=view.min_relevant_query_coverage,
        min_ndcg_delta=view.min_ndcg_delta,
        min_mrr_delta=view.min_mrr_delta,
        min_recall_delta=view.min_recall_delta,
        max_hybrid_p95_ms=view.max_hybrid_p95_ms,
        max_p95_regression_ms=view.max_p95_regression_ms,
        min_semantic_coverage=view.min_semantic_coverage,
        min_slice_judged_queries=view.min_slice_judged_queries,
        max_slice_ndcg_drop=view.max_slice_ndcg_drop,
        required_languages=tuple(view.required_languages),
        required_topics=tuple(view.required_topics),
    )


def _promotion_evaluation_view(model: SearchPromotionEvaluationModel) -> SearchPromotionEvaluationView:
    return SearchPromotionEvaluationView(
        id=model.id,
        policy_id=model.policy_id,
        benchmark_set=model.benchmark_set,
        lexical_run_id=model.lexical_run_id,
        hybrid_run_id=model.hybrid_run_id,
        benchmark_fingerprint=model.benchmark_fingerprint,
        state=model.state,
        checks=[SearchPromotionCheckView(**dict(item)) for item in (model.checks or [])],
        failures=list(model.failures or []),
        warnings=list(model.warnings or []),
        semantic_coverage=dict(model.semantic_coverage or {}),
        methodology_version=model.methodology_version,
        interpretation=model.interpretation,
        created_at=model.created_at,
    )


def _numeric(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _min_numeric(left: object, right: object) -> float | None:
    values = [_numeric(left), _numeric(right)]
    usable = [value for value in values if value is not None]
    return min(usable) if len(usable) == 2 else None


def _numeric_delta(right: object, left: object) -> float | None:
    if not isinstance(right, (int, float)) or not isinstance(left, (int, float)):
        return None
    return round(float(right) - float(left), 6)



def _run_view(item: SearchBenchmarkRunModel) -> SearchBenchmarkRunView:
    return SearchBenchmarkRunView(
        id=item.id,
        benchmark_set=item.benchmark_set,
        search_mode=item.search_mode,
        query_count=item.query_count,
        judged_query_count=item.judged_query_count,
        metrics=dict(item.metrics or {}),
        latency=dict(item.latency or {}),
        metadata=dict(item.metadata_ or {}),
        created_at=item.created_at,
    )


def _latency_payload(values: list[float]) -> dict[str, object]:
    ordered = sorted(values)
    if not ordered:
        return {"p50_ms": None, "p95_ms": None, "mean_ms": None, "max_ms": None}
    return {
        "p50_ms": round(_percentile(ordered, 0.50) or 0.0, 3),
        "p95_ms": round(_percentile(ordered, 0.95) or 0.0, 3),
        "mean_ms": round(mean(ordered), 3),
        "max_ms": round(max(ordered), 3),
    }


def _percentile(ordered: list[float], quantile: float) -> float | None:
    if not ordered:
        return None
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    return round(value, 3)


def _slice_aggregates(
    metric_rows: list[tuple[SearchBenchmarkQueryModel, dict[str, float | None], bool, bool]],
    dimensions: list[str],
) -> dict[str, object]:
    output: dict[str, object] = {}
    for dimension in dimensions:
        groups: dict[str, list[tuple[dict[str, float | None], bool, bool]]] = defaultdict(list)
        for query, metrics, judged, relevant in metric_rows:
            if dimension == "language":
                value = query.language or "unspecified"
            elif dimension == "topic_key":
                value = query.topic_key or "unspecified"
            else:
                value = query.result_type or "all"
            groups[str(value)].append((metrics, judged, relevant))
        dimension_payload: dict[str, object] = {}
        for value, rows in sorted(groups.items()):
            metrics = aggregate_query_metrics([row[0] for row in rows])
            metrics["query_count"] = len(rows)
            metrics["judged_query_count"] = sum(1 for row in rows if row[1])
            metrics["relevant_query_count"] = sum(1 for row in rows if row[2])
            metrics["judgment_coverage"] = round(sum(1 for row in rows if row[1]) / len(rows), 6)
            dimension_payload[value] = metrics
        output[dimension] = dimension_payload
    return output


def _slow_diagnosis(
    result_type: str,
    filters: dict[str, object],
    items: list[SearchQueryObservationModel],
) -> list[str]:
    findings: list[str] = []
    if result_type == "all" and not any(filters.get(key) for key in ("language", "publisher", "lifecycle_status", "from_date", "to_date")):
        findings.append("Broad all-type search with no narrowing filters; ranking must consider the largest retrieval surface.")
    cursor_ratio = sum(1 for item in items if item.cursor_page) / len(items)
    if cursor_ratio >= 0.5:
        findings.append("Most slow observations are cursor pages; inspect keyset continuation and snapshot-selectivity plans.")
    mean_count = mean(int(item.result_count) for item in items)
    if mean_count >= 5_000:
        findings.append("Large matching corpus; verify GIN index usage and filter selectivity with EXPLAIN ANALYZE in a staging database.")
    if filters.get("publisher"):
        findings.append("Publisher text filtering is active; verify publisher lookup/selectivity if this fingerprint remains slow.")
    if result_type == "entity":
        findings.append("Entity retrieval includes canonical-name and approved-alias ranking; inspect alias index usage for this fingerprint.")
    if not findings:
        findings.append("No single filter-shape cause is evident from privacy-preserving telemetry; reproduce this fingerprint in staging with database plan capture.")
    return findings
