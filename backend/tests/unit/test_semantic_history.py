from datetime import UTC, datetime
from uuid import uuid4

import pytest

from newsintel.adapters.semantic.local import SemanticAdapterError, SemanticSearchHit
from newsintel.application.historical.semantic_service import SemanticHistoryService


class _Embedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts
        return [[0.1, 0.2, 0.3]]


class _Index:
    async def search(self, **kwargs):
        assert kwargs["cutoff_epoch"] > 0
        return [
            SemanticSearchHit(
                point_id=str(uuid4()),
                score=0.83,
                payload={
                    "article_version_id": str(uuid4()),
                    "article_id": str(uuid4()),
                    "event_id": str(uuid4()),
                    "publisher": "Archive News",
                    "title": "Earlier policy decision",
                    "source_url": "https://example.com/earlier",
                    "published_at": "2025-01-01T00:00:00+00:00",
                    "retrieved_at": "2025-01-01T01:00:00+00:00",
                    "language": "en",
                },
            )
        ]


@pytest.mark.asyncio
async def test_semantic_history_search_preserves_scope_and_score() -> None:
    service = SemanticHistoryService(
        None,  # type: ignore[arg-type]
        embedder=_Embedder(),  # type: ignore[arg-type]
        index=_Index(),  # type: ignore[arg-type]
        model="test-embedding",
    )
    with pytest.raises(SemanticAdapterError, match="still backfilling"):
        await service.search(
            text="government changes the policy",
            cutoff_at=datetime(2026, 1, 1, tzinfo=UTC),
            exclude_version_id=uuid4(),
            limit=5,
        )

    service._ready = True  # unit-test the retrieval mapping after backfill completion
    result = await service.search(
        text="government changes the policy",
        cutoff_at=datetime(2026, 1, 1, tzinfo=UTC),
        exclude_version_id=uuid4(),
        limit=5,
    )

    assert len(result) == 1
    assert result[0]["semantic_similarity"] == 0.83
    assert result[0]["retrieval_channel"] == "qdrant_local_embedding"
    assert result[0]["semantic_model"] == "test-embedding"
