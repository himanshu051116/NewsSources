"""Prepare recent immutable article versions for fast reader briefs."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB

from newsintel.core.config import get_settings
from newsintel.domain.intelligence.digest_quality import EXCERPT_POLICY, prepare_excerpt
from newsintel.infrastructure.db.models import ArticleModel, ArticleVersionModel
from newsintel.infrastructure.db.session import Database


async def prepare_recent_excerpts(
    factory, *, days: int = 8, limit: int = 20000, batch_size: int = 150
) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    total = 0
    while total < limit:
        async with factory() as session:
            rows = (
                (
                    await session.execute(
                        select(
                            ArticleVersionModel.id,
                            ArticleVersionModel.title,
                            func.left(ArticleVersionModel.text_content, 6000).label("text"),
                            func.coalesce(
                                ArticleVersionModel.published_at,
                                ArticleModel.published_at,
                                ArticleModel.first_observed_at,
                            ).label("published_at"),
                        )
                        .join(ArticleModel, ArticleModel.id == ArticleVersionModel.article_id)
                        .where(
                            or_(
                                ArticleVersionModel.created_at >= cutoff,
                                ArticleVersionModel.published_at >= cutoff,
                            ),
                            ArticleVersionModel.metadata_["digest_excerpt"][
                                "policy"
                            ].astext.is_distinct_from(EXCERPT_POLICY),
                        )
                        .order_by(ArticleVersionModel.created_at.desc(), ArticleVersionModel.id)
                        .limit(min(batch_size, limit - total))
                    )
                )
                .mappings()
                .all()
            )
        if not rows:
            break
        # No open DB transaction during text analysis.
        values = await asyncio.to_thread(
            lambda batch=rows: [
                (row["id"], prepare_excerpt(row["text"], row["title"], row["published_at"].year))
                for row in batch
            ]
        )
        async with factory() as session, session.begin():
            for version_id, prepared in values:
                await session.execute(
                    update(ArticleVersionModel)
                    .where(
                        ArticleVersionModel.id == version_id,
                    )
                    .values(
                        metadata_=func.coalesce(ArticleVersionModel.metadata_, cast({}, JSONB)).op(
                            "||"
                        )(cast({"digest_excerpt": prepared}, JSONB))
                    )
                )
        total += len(values)
        print(f"Prepared {total} article versions", flush=True)
    return total


async def main(days: int, limit: int) -> None:
    database = Database(get_settings())
    try:
        await prepare_recent_excerpts(database.session_factory, days=days, limit=limit)
    finally:
        await database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 31), default=8)
    parser.add_argument("--limit", type=int, choices=range(1, 100001), default=20000)
    args = parser.parse_args()
    asyncio.run(main(args.days, args.limit))
