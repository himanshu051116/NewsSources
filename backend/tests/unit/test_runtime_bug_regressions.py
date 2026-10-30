import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from newsintel.adapters.artifacts.local_store import RawFetchArtifact
from newsintel.adapters.http.safe_fetcher import FetchResult
from newsintel.application.articles.processing import ArticleWorker, LeasedUrlCandidate
from newsintel.application.historical.enrichment_service import _score_semantic_matches
from newsintel.application.search.quality_service import SearchQualityService
from newsintel.application.sources.service import _looks_like_html_payload
from newsintel.infrastructure.db.article_processing_repository import _assert_candidate_lease
from newsintel.infrastructure.db.models import ArticleFetchRunModel, SearchBenchmarkQueryModel


def test_fetch_run_accepts_migrated_lineage_fields() -> None:
    job_id = uuid4()
    run = ArticleFetchRunModel(fetch_job_id=job_id, lease_version=7)
    assert run.fetch_job_id == job_id
    assert run.lease_version == 7
    assert {"fetch_job_id", "lease_version"} <= set(ArticleFetchRunModel.__table__.columns.keys())


def test_raw_snapshot_metadata_is_json_serializable() -> None:
    import json

    artifact = RawFetchArtifact("file:///snapshot.html", "local_filesystem", "a" * 64, 40)
    metadata = json.loads(json.dumps(artifact.to_metadata()))
    assert metadata["artifact_uri"] == artifact.artifact_uri
    assert metadata["sha256"] == artifact.sha256
    assert metadata["byte_size"] == 40


@pytest.mark.parametrize(
    ("body", "expected"),
    [(b"  <!DOCTYPE HTML><html>News</html>", True), (b"<HTML>News</HTML>", True),
     (b'{"items": []}', False), (b"<rss></rss>", False)],
)
def test_discovery_sniffs_missing_content_type(body: bytes, expected: bool) -> None:
    result = FetchResult(
        requested_url="https://example.org/", final_url="https://example.org/",
        status_code=200, headers={}, body=body, body_sha256="a" * 64,
        retrieved_at=datetime.now(UTC), redirect_chain=(),
    )
    assert _looks_like_html_payload(result) is expected


def test_semantic_history_scores_use_entity_phrases_and_preserve_provenance() -> None:
    original = {"title": "Reserve Bank changes rates", "semantic_similarity": 0.8,
                "source_url": "https://example.org/old"}
    result = _score_semantic_matches(
        [original], current_entities={"reserve bank"}, current_terms={"bank", "rates"},
    )[0]
    assert result["relevance_signals"]["entity_overlap"] == 1.0
    assert result["relevance_signals"]["lexical_overlap"] == 1.0
    assert result["relevance_score"] == pytest.approx(0.84)
    assert result["source_url"] == original["source_url"]
    assert "relevance_score" not in original


@pytest.mark.asyncio
async def test_benchmark_export_does_not_require_semantic_runtime() -> None:
    query = SearchBenchmarkQueryModel(
        id=uuid4(), query_text="policy", result_type="event", filters={}, language="en",
        topic_key=None, notes=None, case_key="case-1",
    )
    session = AsyncMock()
    session.scalars.side_effect = [SimpleNamespace(all=lambda: [query]),
                                   SimpleNamespace(all=lambda: [])]
    manager = AsyncMock()
    manager.__aenter__.return_value = session
    service = SearchQualityService(lambda: manager)
    bundle = await service.export_bundle("test")
    assert bundle.benchmark_set == "test"
    assert bundle.queries[0].result_type == "event"
    assert bundle.queries[0].judgments == []


@pytest.mark.parametrize("defect", ["expired", "wrong_state", "wrong_version", "wrong_owner"])
def test_article_mutations_reject_stale_leases(defect: str) -> None:
    candidate = LeasedUrlCandidate(
        id=uuid4(), publisher_id=uuid4(), normalized_url="https://example.org/story",
        attempt_count=1, lease_version=2, lease_owner="worker-a",
    )
    row = SimpleNamespace(
        state="leased", lease_owner="worker-a", lease_version=2,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
    )
    if defect == "expired":
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif defect == "wrong_state":
        row.state = "processed"
    elif defect == "wrong_version":
        row.lease_version = 3
    else:
        row.lease_owner = "worker-b"
    with pytest.raises(RuntimeError, match="lease lost"):
        _assert_candidate_lease(row, candidate)


@pytest.mark.asyncio
async def test_article_worker_does_not_lease_jobs_waiting_for_a_slot() -> None:
    repository = AsyncMock()
    repository.lease_due_candidates.return_value = ()
    worker = ArticleWorker(repository=repository, processor=AsyncMock(), worker_id="test",
                           batch_size=20, concurrency=2)
    assert await worker.run_once() == 0
    assert repository.lease_due_candidates.call_args.kwargs["limit"] == 2


@pytest.mark.asyncio
async def test_worker_database_failure_drains_other_tasks_before_returning() -> None:
    repository = AsyncMock()
    candidates = [LeasedUrlCandidate(id=uuid4(), publisher_id=uuid4(),
                  normalized_url="https://example.org/story", attempt_count=1) for _ in range(2)]
    repository.lease_due_candidates.return_value = candidates
    finished = asyncio.Event()

    async def process(candidate, *, worker_id):
        if candidate is candidates[0]:
            raise OSError("database unavailable")
        await asyncio.sleep(0.01)
        finished.set()

    processor = SimpleNamespace(process=process)
    worker = ArticleWorker(repository=repository, processor=processor, worker_id="test",
                           concurrency=2)
    with pytest.raises(OSError, match="database unavailable"):
        await worker.run_once()
    assert finished.is_set()
