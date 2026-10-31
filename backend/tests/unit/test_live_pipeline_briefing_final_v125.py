from pathlib import Path

from newsintel import __version__
from newsintel.application.briefings.service import BRIEFING_METHODOLOGY_VERSION
from newsintel.core.schema import EXPECTED_SCHEMA_REVISION

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"


def test_final_release_identity_and_schema() -> None:
    assert __version__ == "1.25.0"
    assert EXPECTED_SCHEMA_REVISION == "0034_article_revision_history"
    assert BRIEFING_METHODOLOGY_VERSION == "grounded-event-briefing-v1"


def test_live_pipeline_migration_contains_fencing_and_identity() -> None:
    text = (BACKEND_ROOT / "migrations/versions/0032_live_pipeline_hardening.py").read_text(encoding="utf-8")
    for required in (
        "lease_version",
        "lease_heartbeat_at",
        "fetch_job_observations",
        "article_identities",
        "article_identity_members",
    ):
        assert required in text


def test_grounded_explainer_migration_and_worker_exist() -> None:
    migration = (BACKEND_ROOT / "migrations/versions/0033_grounded_news_explainer.py").read_text(encoding="utf-8")
    assert "event_briefing_jobs" in migration
    assert "event_briefings" in migration
    worker = (BACKEND_ROOT / "src/newsintel/workers/briefings.py").read_text(encoding="utf-8")
    assert "lease_next" in worker
    assert "heartbeat" in worker
    service = (BACKEND_ROOT / "src/newsintel/application/briefings/service.py").read_text(encoding="utf-8")
    assert "stored platform records only" in service
    assert "evidence_ids" in service


def test_final_deployment_assets_exist() -> None:
    project_root = PROJECT_ROOT
    for rel in (
        "Dockerfile",
        "compose.production.yaml",
        ".env.production.example",
        "deploy/Caddyfile",
        "PRODUCTION-RUNBOOK.md",
        ".github/workflows/ci.yml",
        "scripts/production-smoke.sh",
        "scripts/production-backup.sh",
        "scripts/production-restore.sh",
    ):
        assert (project_root / rel).is_file(), rel
