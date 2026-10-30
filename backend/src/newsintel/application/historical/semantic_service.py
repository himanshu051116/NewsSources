from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.adapters.semantic.local import (
    OllamaEmbeddingClient,
    QdrantSemanticIndex,
    SemanticAdapterError,
)
from newsintel.infrastructure.db.models import (
    ArticleModel,
    ArticleVersionModel,
    PublisherModel,
)


class SemanticHistoryService:
    """Optional local semantic index/search for article history.

    PostgreSQL remains the source of truth. Qdrant contains derived vectors only and
    can be rebuilt safely from article_versions.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        embedder: OllamaEmbeddingClient,
        index: QdrantSemanticIndex,
        model: str,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._index = index
        self._model = model
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def index_missing(self, *, limit: int = 32) -> int:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(ArticleVersionModel, ArticleModel, PublisherModel)
                    .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                    .join(PublisherModel, PublisherModel.id == ArticleModel.publisher_id)
                    .where(
                        or_(
                            ArticleVersionModel.semantic_indexed_at.is_(None),
                            ArticleVersionModel.semantic_model.is_distinct_from(self._model),
                            ArticleVersionModel.semantic_content_sha256.is_distinct_from(
                                ArticleVersionModel.content_sha256
                            ),
                        )
                    )
                    .order_by(ArticleVersionModel.created_at)
                    .limit(max(1, min(limit, 256)))
                )
            ).all()
        if not rows:
            self._ready = True
            return 0

        self._ready = False
        texts = [_embedding_text(version) for version, _article, _publisher in rows]
        vectors = await self._embedder.embed(texts)
        if len(vectors) != len(rows):
            raise RuntimeError("semantic embedding count did not match article batch")
        dimension = len(vectors[0])
        await self._index.ensure_collection(dimension)
        points: list[dict[str, object]] = []
        for vector, (version, article, publisher) in zip(vectors, rows, strict=True):
            observed = version.published_at or version.retrieved_at
            points.append(
                {
                    "id": str(version.id),
                    "vector": vector,
                    "payload": {
                        "article_version_id": str(version.id),
                        "article_id": str(article.id),
                        "event_id": str(article.event_id),
                        "publisher_id": str(publisher.id),
                        "publisher": publisher.name,
                        "title": version.title,
                        "source_url": version.final_url,
                        "published_at": _iso(version.published_at),
                        "retrieved_at": _iso(version.retrieved_at),
                        "observed_at_epoch": observed.timestamp(),
                        "content_sha256": version.content_sha256,
                        "language": version.language,
                    },
                }
            )
        await self._index.upsert(points)

        now = datetime.now(UTC)
        version_ids = [version.id for version, _article, _publisher in rows]
        async with self._session_factory() as session, session.begin():
            persisted = list(
                (
                    await session.scalars(
                        select(ArticleVersionModel)
                        .where(ArticleVersionModel.id.in_(version_ids))
                        .with_for_update()
                    )
                ).all()
            )
            for version in persisted:
                version.semantic_indexed_at = now
                version.semantic_model = self._model
                version.semantic_content_sha256 = version.content_sha256
        return len(rows)

    async def search(
        self,
        *,
        text: str,
        cutoff_at: datetime,
        exclude_version_id: UUID,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        if not self._ready:
            raise SemanticAdapterError("semantic article index is still backfilling")
        vectors = await self._embedder.embed([text])
        if not vectors:
            return []
        hits = await self._index.search(
            vector=vectors[0],
            limit=limit,
            cutoff_epoch=cutoff_at.timestamp(),
            exclude_point_id=str(exclude_version_id),
        )
        output: list[dict[str, object]] = []
        for hit in hits:
            payload = hit.payload
            output.append(
                {
                    "article_id": payload.get("article_id"),
                    "article_version_id": payload.get("article_version_id"),
                    "event_id": payload.get("event_id"),
                    "publisher": payload.get("publisher"),
                    "title": payload.get("title"),
                    "url": payload.get("source_url"),
                    "published_at": payload.get("published_at"),
                    "retrieved_at": payload.get("retrieved_at"),
                    "language": payload.get("language"),
                    "relationship": "semantic_historical_match",
                    "semantic_similarity": round(hit.score, 6),
                    "retrieval_channel": "qdrant_local_embedding",
                    "semantic_model": self._model,
                }
            )
        return output


def _embedding_text(version: ArticleVersionModel) -> str:
    title = " ".join(version.title.split())
    body = " ".join(version.text_content.split())[:10_000]
    return f"{title}\n\n{body}".strip()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
