"""Read-only live reader → API → stored-version publication checks."""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

from newsintel.core.config import get_settings
from newsintel.infrastructure.db.models import ArticleVersionModel
from newsintel.infrastructure.db.session import Database


async def main():
    evidence = {}
    database = Database(get_settings())
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8010", timeout=120) as client:
            for route in ("/briefs", "/news"):
                page = await client.get(route)
                page.raise_for_status()
                assert 'class="reader-layout"' in page.text
                assert page.headers["cache-control"] == "private, no-store"
            csrf = client.cookies.get("newsintel_csrf")
            if csrf:
                client.headers["X-CSRF-Token"] = csrf

            async def preview(**command):
                response = await client.post("/api/v1/digests/preview", json=command)
                response.raise_for_status()
                return response.json()

            for period in ("daily", "weekly"):
                started = time.perf_counter()
                edition = await preview(period=period)
                assert edition["items"], "Expected readable recent reporting from the local publishers"
                assert edition["word_count"] <= 360 and edition["estimated_read_seconds"] <= 120
                start, end = (datetime.fromisoformat(edition[key]) for key in ("window_start", "window_end"))
                async with database.session_factory() as session:
                    for item in edition["items"]:
                        assert item["date_basis"] == "published" and item["freshness_status"] == "current"
                        assert item["summary_available"]
                        published = datetime.fromisoformat(item["published_at"])
                        assert start <= published < end
                        version = await session.scalar(select(ArticleVersionModel).where(
                            ArticleVersionModel.article_id == UUID(item["article_id"]),
                            ArticleVersionModel.created_at <= end,
                        ).order_by(ArticleVersionModel.version_number.desc()).limit(1))
                        assert version and version.published_at == published
                        assert version.title == item["title"]
                evidence[period] = {"seconds": round(time.perf_counter()-started, 3), "edition": edition}
                latest = await preview(period=period, as_of=edition["window_end"], full_stream=True,
                                       current_only=True, page_size=5)
                assert all(item["freshness_status"] == "current" and item["date_basis"] == "published"
                           for item in latest["items"])
                if latest["next_offset"] is not None:
                    following = await preview(period=period, as_of=edition["window_end"], full_stream=True,
                        current_only=True, page_size=5, offset=latest["next_offset"])
                    assert not ({i["article_id"] for i in latest["items"]}
                                & {i["article_id"] for i in following["items"]})
                evidence[period]["latest_stream_sample"] = latest
                print(period, len(edition["items"]), "current stories;",
                      edition["excluded_stale_or_uncertain"], "flagged stories kept out;",
                      evidence[period]["seconds"], "seconds", flush=True)
        output = Path(__file__).resolve().parents[1] / ".run/audit/reader-freshness-live-20261030.json"
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
