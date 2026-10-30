from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from newsintel.api.dependencies import (
    AnalystAuth,
    ClaimVerifierAuth,
    SearchQualityServiceDependency,
)
from newsintel.application.search.dto import (
    SearchBenchmarkBundle,
    SearchBenchmarkComparisonView,
    SearchBenchmarkImportCommand,
    SearchBenchmarkImportView,
    SearchBenchmarkQueryCreateCommand,
    SearchBenchmarkQueryView,
    SearchBenchmarkRunCommand,
    SearchBenchmarkRunView,
    SearchExperimentStatusView,
    SearchRelevanceJudgmentCommand,
    SearchRelevanceJudgmentView,
    SearchSlowDiagnosticsView,
    SearchTelemetryView,
    SearchSemanticCoverageView,
    SearchPromotionPolicyCommand,
    SearchPromotionPolicyView,
    SearchPromotionEvaluationView,
    SearchPromotionDecisionCommand,
    SearchPromotionDecisionView,
)

router = APIRouter(tags=["search-quality"])


@router.get("/search-quality/experiment-status", response_model=SearchExperimentStatusView)
async def search_experiment_status(
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> SearchExperimentStatusView:
    return service.experiment_status()


@router.get("/search-quality/telemetry", response_model=SearchTelemetryView)
async def search_telemetry(
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
    window_hours: int = Query(default=24, ge=1, le=720),
) -> SearchTelemetryView:
    try:
        return await service.telemetry(window_hours=window_hours)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc




@router.get("/search-quality/slow-diagnostics", response_model=SearchSlowDiagnosticsView)
async def search_slow_diagnostics(
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
    window_hours: int = Query(default=24, ge=1, le=720),
    threshold_ms: float = Query(default=750.0, ge=1, le=120000),
    limit: int = Query(default=30, ge=1, le=100),
) -> SearchSlowDiagnosticsView:
    try:
        return await service.slow_diagnostics(window_hours=window_hours, threshold_ms=threshold_ms, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/search-quality/semantic-coverage", response_model=SearchSemanticCoverageView)
async def search_semantic_coverage(
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> SearchSemanticCoverageView:
    return await service.semantic_coverage()


@router.get("/search-quality/{benchmark_set}/promotion-policy", response_model=SearchPromotionPolicyView)
async def get_search_promotion_policy(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> SearchPromotionPolicyView:
    return await service.promotion_policy(benchmark_set)


@router.put("/search-quality/{benchmark_set}/promotion-policy", response_model=SearchPromotionPolicyView)
async def save_search_promotion_policy(
    benchmark_set: str,
    command: SearchPromotionPolicyCommand,
    auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchPromotionPolicyView:
    return await service.save_promotion_policy(benchmark_set, command, actor_user_id=auth.id)


@router.post("/search-quality/{benchmark_set}/promotion-gate/evaluate", response_model=SearchPromotionEvaluationView)
async def evaluate_search_promotion_gate(
    benchmark_set: str,
    auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchPromotionEvaluationView:
    return await service.evaluate_promotion_gate(benchmark_set, actor_user_id=auth.id)


@router.get("/search-quality/{benchmark_set}/promotion-gate/history", response_model=list[SearchPromotionEvaluationView])
async def search_promotion_gate_history(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[SearchPromotionEvaluationView]:
    return await service.promotion_history(benchmark_set, limit=limit)


@router.post("/search-quality/promotion-gate/{evaluation_id}/decisions", response_model=SearchPromotionDecisionView)
async def record_search_promotion_decision(
    evaluation_id: UUID,
    command: SearchPromotionDecisionCommand,
    auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchPromotionDecisionView:
    try:
        result = await service.record_promotion_decision(evaluation_id, command, actor_user_id=auth.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="promotion evaluation not found")
    return result


@router.get("/search-quality/{benchmark_set}/promotion-decisions", response_model=list[SearchPromotionDecisionView])
async def list_search_promotion_decisions(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
    limit: int = Query(default=30, ge=1, le=100),
) -> list[SearchPromotionDecisionView]:
    return await service.promotion_decisions(benchmark_set, limit=limit)


@router.post("/search-quality/import", response_model=SearchBenchmarkImportView)
async def import_search_benchmark(
    command: SearchBenchmarkImportCommand,
    auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchBenchmarkImportView:
    return await service.import_bundle(command, actor_user_id=auth.id)


@router.post("/search-quality/queries", response_model=SearchBenchmarkQueryView)
async def create_search_benchmark_query(
    command: SearchBenchmarkQueryCreateCommand,
    auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchBenchmarkQueryView:
    try:
        return await service.create_query(command, actor_user_id=auth.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/search-quality/{benchmark_set}/queries", response_model=list[SearchBenchmarkQueryView])
async def list_search_benchmark_queries(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> list[SearchBenchmarkQueryView]:
    return await service.list_queries(benchmark_set)


@router.post(
    "/search-quality/queries/{query_id}/judgments",
    response_model=SearchRelevanceJudgmentView,
)
async def upsert_search_relevance_judgment(
    query_id: UUID,
    command: SearchRelevanceJudgmentCommand,
    auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchRelevanceJudgmentView:
    result = await service.upsert_judgment(query_id, command, actor_user_id=auth.id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="benchmark query not found")
    return result


@router.get(
    "/search-quality/queries/{query_id}/judgments",
    response_model=list[SearchRelevanceJudgmentView],
)
async def list_search_relevance_judgments(
    query_id: UUID,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> list[SearchRelevanceJudgmentView]:
    result = await service.list_judgments(query_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="benchmark query not found")
    return result


@router.get("/search-quality/{benchmark_set}/export", response_model=SearchBenchmarkBundle)
async def export_search_benchmark(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> SearchBenchmarkBundle:
    try:
        return await service.export_bundle(benchmark_set)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/search-quality/{benchmark_set}/evaluate", response_model=SearchBenchmarkRunView)
async def evaluate_search_benchmark(
    benchmark_set: str,
    command: SearchBenchmarkRunCommand,
    _auth: ClaimVerifierAuth,
    service: SearchQualityServiceDependency,
) -> SearchBenchmarkRunView:
    try:
        return await service.evaluate(benchmark_set, command)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/search-quality/{benchmark_set}/compare", response_model=SearchBenchmarkComparisonView)
async def compare_search_benchmark_modes(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
) -> SearchBenchmarkComparisonView:
    return await service.compare_latest_modes(benchmark_set)


@router.get("/search-quality/{benchmark_set}/runs", response_model=list[SearchBenchmarkRunView])
async def search_benchmark_history(
    benchmark_set: str,
    _auth: AnalystAuth,
    service: SearchQualityServiceDependency,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SearchBenchmarkRunView]:
    return await service.history(benchmark_set, limit=limit)
