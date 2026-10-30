from fastapi.testclient import TestClient

from newsintel.main import create_app


def test_liveness_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.headers["server-timing"].startswith("app;dur=")
    assert response.json() == {
        "status": "ok",
        "service": "news-intelligence-api",
    }


def test_openapi_exposes_synchronized_acquisition_endpoints() -> None:
    schema = create_app().openapi()

    assert "/api/v1/admin/publishers" in schema["paths"]
    assert "/api/v1/admin/discovery-channels" in schema["paths"]
    assert "/api/v1/admin/discovery-channels/{channel_id}/poll" in schema["paths"]
    assert "/api/v1/internal/discoveries" in schema["paths"]
    assert "/api/v1/articles" in schema["paths"]
    assert "/briefs" in schema["paths"]
    assert "/api/v1/digests/preview" in schema["paths"]
    assert "/api/v1/digest-streams/{stream_id}" in schema["paths"]
    assert "/api/v1/articles/{article_id}" in schema["paths"]
    assert "/api/v1/articles/{article_id}/claims" in schema["paths"]
    assert "/api/v1/articles/{article_id}/quality" in schema["paths"]
    assert "/api/v1/search/deployment" in schema["paths"]
    assert "/api/v1/search/deployment/rollback" in schema["paths"]
    assert "/api/v1/search/deployment/outcome" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/verify" in schema["paths"]
    assert "/api/v1/events/{event_id}" in schema["paths"]
    assert "/api/v1/historical/internal/search" in schema["paths"]
    assert "/api/v1/historical/articles/{article_id}/versions" in schema["paths"]
    assert "/api/v1/historical/articles/{article_id}/claim-history" in schema["paths"]
    assert "/api/v1/historical/events/{event_id}/timeline" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/evidence-search/{run_id}/execute" in schema["paths"]
    assert "/api/v1/publishers/{publisher_id}/reliability/recompute" in schema["paths"]
    assert "/api/v1/publishers/{publisher_id}/reliability" in schema["paths"]
    assert "/api/v1/historical/events/{event_id}/knowledge-graph/rebuild" in schema["paths"]
    assert "/api/v1/historical/events/{event_id}/knowledge-graph" in schema["paths"]
    assert "/api/v1/historical/events/{event_id}/knowledge-graph/diff" in schema["paths"]
    assert "/api/v1/ownership-groups" in schema["paths"]
    assert "/api/v1/ownership-groups/{group_id}/publishers/{publisher_id}" in schema["paths"]
    assert "/api/v1/publishers/{publisher_id}/ownership" in schema["paths"]
    assert "/api/v1/entities/resolve" in schema["paths"]
    assert "/api/v1/entities/{entity_id}/aliases" in schema["paths"]
    assert "/api/v1/verification-calibration/cases" in schema["paths"]
    assert "/api/v1/verification-calibration/{benchmark_set}/assess" in schema["paths"]
    assert "/api/v1/verification-calibration/{benchmark_set}" in schema["paths"]
    assert "/api/v1/historical/knowledge-graph/search" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/evidence-search/{run_id}/orchestrate" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/conflict-resolution" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}/assess" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}/audit" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}/agreement" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}/diagnostics" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}/validation-report" in schema["paths"]
    assert "/api/v1/entities/{entity_id}/external-identifiers" in schema["paths"]
    assert "/api/v1/ownership-memberships/{membership_id}/provenance" in schema["paths"]
    assert "/api/v1/historical/events/{event_id}/knowledge-graph/neighborhood" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/evidence-search/{run_id}/stopping-assessment" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/evidence-search/stopping-history" in schema["paths"]
    assert "/api/v1/historical/articles/{article_id}/corrections/detect" in schema["paths"]
    assert "/api/v1/historical/articles/{article_id}/corrections" in schema["paths"]
    assert "/api/v1/claim-review-flags/{flag_id}/resolve" in schema["paths"]
    assert "/api/v1/verification-benchmark/{benchmark_set}/quality-gate" in schema["paths"]
    assert "/api/v1/entity-registries" in schema["paths"]
    assert "/api/v1/entities/{entity_id}/registry-link" in schema["paths"]
    assert "/api/v1/ownership/ingest" in schema["paths"]
    assert "/api/v1/corrections/{correction_event_id}/dependency-propagation" in schema["paths"]
    assert "/api/v1/claims/{claim_id}/verification-manifests" in schema["paths"]
    assert "/api/v1/verification-manifests/backfill" in schema["paths"]
    assert "/api/v1/system/release-readiness/{benchmark_set}" in schema["paths"]
    assert "/api/v1/publishers" in schema["paths"]
    assert "/api/v1/publishers/discover" in schema["paths"]
    assert "/api/v1/publishers/{publisher_id}/fetch" in schema["paths"]
    assert "/api/v1/fetch/all" in schema["paths"]
    assert "/api/v1/fetch-jobs/{job_id}" in schema["paths"]
    assert "/news-sources" in schema["paths"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
