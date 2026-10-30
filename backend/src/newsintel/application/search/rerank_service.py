from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from newsintel.adapters.semantic.local import (
    OllamaEmbeddingClient,
    QdrantSemanticIndex,
    SemanticAdapterError,
)
from newsintel.application.articles.dto import IntelligenceSearchResultView, IntelligenceSearchView
from newsintel.infrastructure.db.models import ArticleVersionModel


class SemanticRerankUnavailableError(RuntimeError):
    """Raised when a controlled semantic experiment cannot be executed safely."""


@dataclass(frozen=True, slots=True)
class SemanticRerankConfig:
    model: str
    semantic_limit: int = 100
    rrf_k: int = 60
    semantic_weight: float = 1.0


class SemanticArticleReranker:
    """Experiment-only article reranker over an existing lexical candidate pool.

    It never introduces semantically-only results. This keeps recall scope tied to
    the production lexical search while allowing benchmarked changes in ordering.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedder: OllamaEmbeddingClient,
        index: QdrantSemanticIndex,
        config: SemanticRerankConfig,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._index = index
        self._config = config

    @property
    def model(self) -> str:
        return self._config.model

    async def rerank(
        self,
        *,
        query: str,
        lexical: IntelligenceSearchView,
        limit: int,
        preserve_cursor: bool = False,
        mode_label: str = "hybrid_article_rerank_v1",
    ) -> IntelligenceSearchView:
        if not lexical.results:
            return lexical.model_copy(update={"search_mode": mode_label})
        if any(item.result_type != "article" for item in lexical.results):
            raise ValueError("semantic reranking experiments currently support article-only search")
        snapshot_at = lexical.snapshot_at
        if snapshot_at is None:
            raise SemanticRerankUnavailableError("lexical search did not provide a retrieval snapshot")
        indexed_count = await self._indexed_current_version_count(snapshot_at)
        if indexed_count <= 0:
            raise SemanticRerankUnavailableError("no current article versions are marked as semantically indexed")

        vectors = await self._embedder.embed([query])
        if not vectors:
            raise SemanticRerankUnavailableError("embedding service returned no query vector")
        try:
            hits = await self._index.search(
                vector=vectors[0],
                limit=max(10, min(self._config.semantic_limit, 100)),
                cutoff_epoch=snapshot_at.timestamp() + 0.000001,
                create_if_missing=False,
            )
        except SemanticAdapterError as exc:
            raise SemanticRerankUnavailableError(str(exc)) from exc
        if not hits:
            raise SemanticRerankUnavailableError(
                "semantic index returned no hits; verify the local embedding/Qdrant index is populated"
            )

        current_versions = await self._current_versions_for_hits(hits, snapshot_at)
        semantic_rank: dict[UUID, tuple[int, float]] = {}
        rank = 0
        for hit in hits:
            article_raw = hit.payload.get("article_id")
            version_raw = hit.payload.get("article_version_id")
            if not article_raw or not version_raw:
                continue
            try:
                article_id = UUID(str(article_raw))
                version_id = UUID(str(version_raw))
            except ValueError:
                continue
            if current_versions.get(article_id) != version_id:
                continue
            rank += 1
            previous = semantic_rank.get(article_id)
            if previous is None or hit.score > previous[1]:
                semantic_rank[article_id] = (rank, float(hit.score))

        reranked: list[tuple[float, int, IntelligenceSearchResultView]] = []
        for lexical_rank, item in enumerate(lexical.results, start=1):
            semantic = semantic_rank.get(item.id)
            semantic_position = semantic[0] if semantic is not None else None
            rrf = reciprocal_rank_fusion_score(
                lexical_rank=lexical_rank,
                semantic_rank=semantic_position,
                k=self._config.rrf_k,
                semantic_weight=self._config.semantic_weight,
            )
            metadata = dict(item.metadata)
            metadata["lexical_rank"] = lexical_rank
            if semantic is not None:
                semantic_position, similarity = semantic
                metadata.update(
                    {
                        "semantic_rank": semantic_position,
                        "semantic_similarity": round(similarity, 6),
                        "semantic_model": self._config.model,
                    }
                )
            else:
                metadata.update({"semantic_rank": None, "semantic_similarity": None})
            metadata["rerank_score"] = round(rrf, 10)
            reranked.append(
                (
                    rrf,
                    lexical_rank,
                    item.model_copy(update={"metadata": metadata, "score": rrf}),
                )
            )

        reranked.sort(key=lambda value: (-value[0], value[1]))
        results = [item for _score, _lexical_rank, item in reranked[:limit]]
        return lexical.model_copy(
            update={
                "results": results,
                "next_cursor": lexical.next_cursor if preserve_cursor else None,
                "search_mode": mode_label,
            }
        )

    async def _indexed_current_version_count(self, snapshot_at: datetime) -> int:
        newer = aliased(ArticleVersionModel)
        statement = (
            select(ArticleVersionModel.id)
            .where(
                ArticleVersionModel.semantic_indexed_at.is_not(None),
                ArticleVersionModel.created_at <= snapshot_at,
                ~exists(
                    select(1).where(
                        newer.article_id == ArticleVersionModel.article_id,
                        newer.version_number > ArticleVersionModel.version_number,
                        newer.created_at <= snapshot_at,
                    )
                ),
            )
            .limit(1)
        )
        async with self._session_factory() as session:
            return 1 if await session.scalar(statement) is not None else 0

    async def _current_versions_for_hits(self, hits, snapshot_at: datetime) -> dict[UUID, UUID]:
        article_ids: set[UUID] = set()
        for hit in hits:
            raw = hit.payload.get("article_id")
            if not raw:
                continue
            try:
                article_ids.add(UUID(str(raw)))
            except ValueError:
                continue
        if not article_ids:
            return {}
        newer = aliased(ArticleVersionModel)
        statement = select(ArticleVersionModel.article_id, ArticleVersionModel.id).where(
            ArticleVersionModel.article_id.in_(article_ids),
            ArticleVersionModel.created_at <= snapshot_at,
            ~exists(
                select(1).where(
                    newer.article_id == ArticleVersionModel.article_id,
                    newer.version_number > ArticleVersionModel.version_number,
                    newer.created_at <= snapshot_at,
                )
            ),
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        return {article_id: version_id for article_id, version_id in rows}


def reciprocal_rank_fusion_score(
    *,
    lexical_rank: int,
    semantic_rank: int | None,
    k: int = 60,
    semantic_weight: float = 1.0,
) -> float:
    if lexical_rank < 1:
        raise ValueError("lexical_rank must be >= 1")
    if semantic_rank is not None and semantic_rank < 1:
        raise ValueError("semantic_rank must be >= 1")
    if k < 1:
        raise ValueError("k must be >= 1")
    score = 1.0 / (k + lexical_rank)
    if semantic_rank is not None:
        score += max(0.0, semantic_weight) * (1.0 / (k + semantic_rank))
    return score
