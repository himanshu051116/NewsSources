from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from newsintel.application.historical.dto import (
    InternalHistoricalMatchView,
    InternalHistoricalSearchCommand,
    InternalHistoricalSearchResponse,
)
from newsintel.infrastructure.db.models import (
    ArticleClaimModel,
    ArticleModel,
    ArticleVersionModel,
)


class InternalHistoricalSearchService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def search(
        self,
        command: InternalHistoricalSearchCommand,
    ) -> InternalHistoricalSearchResponse:
        observed_time = func.coalesce(
            ArticleVersionModel.published_at,
            ArticleVersionModel.retrieved_at,
        )
        document = func.to_tsvector(
            "simple",
            func.coalesce(ArticleVersionModel.title, "")
            + " "
            + func.coalesce(ArticleVersionModel.text_content, ""),
        )
        search_query = func.websearch_to_tsquery("simple", command.query)
        rank = func.ts_rank_cd(document, search_query).label("fts_rank")
        statement = (
            select(ArticleVersionModel, ArticleModel, rank)
            .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
            .where(document.op("@@")(search_query))
        )
        if command.from_date is not None:
            start = datetime.combine(command.from_date, time.min, tzinfo=UTC)
            statement = statement.where(observed_time >= start)
        if command.to_date is not None:
            end = datetime.combine(command.to_date, time.max, tzinfo=UTC)
            statement = statement.where(observed_time <= end)
        statement = statement.order_by(rank.desc(), observed_time.desc()).limit(command.limit)

        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).all())
            version_ids = [version.id for version, _article, _rank in rows]
            claim_counts: dict[object, int] = defaultdict(int)
            if version_ids:
                counts = (
                    await session.execute(
                        select(
                            ArticleClaimModel.article_version_id,
                            func.count(ArticleClaimModel.id),
                        )
                        .where(ArticleClaimModel.article_version_id.in_(version_ids))
                        .group_by(ArticleClaimModel.article_version_id)
                    )
                ).all()
                for version_id, count in counts:
                    claim_counts[version_id] = int(count)

        results = [
            InternalHistoricalMatchView(
                article_id=article.id,
                event_id=article.event_id,
                article_version_id=version.id,
                version_number=version.version_number,
                title=version.title,
                url=version.final_url,
                published_at=version.published_at,
                retrieved_at=version.retrieved_at,
                snippet=_snippet(version.text_content, command.query),
                claim_count=claim_counts.get(version.id, 0),
                metadata={
                    "content_sha256": version.content_sha256,
                    "extraction_method": version.extraction_method,
                    "lineage": version.metadata_.get("content_lineage"),
                    "fts_rank": round(float(fts_rank or 0.0), 6),
                },
            )
            for version, article, fts_rank in rows
        ]
        observed = [item.retrieved_at for item in results]
        return InternalHistoricalSearchResponse(
            query=command.query,
            from_date=command.from_date,
            to_date=command.to_date,
            results=results,
            result_count=len(results),
            event_count=len({item.event_id for item in results}),
            earliest_observed_at=min(observed) if observed else None,
            latest_observed_at=max(observed) if observed else None,
            generated_at=datetime.now(UTC),
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _snippet(text: str, query: str, *, radius: int = 220) -> str:
    normalized_query = query.strip().lower()
    lowered = text.lower()
    index = lowered.find(normalized_query)
    if index < 0:
        return " ".join(text.split())[: radius * 2]
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    snippet = " ".join(text[start:end].split())
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(text):
        snippet = f"{snippet}…"
    return snippet
