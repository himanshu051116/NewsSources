"""Re-extract selected briefs' archived HTML without changing stored reporting."""
import asyncio
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname
from uuid import UUID

from sqlalchemy import select

from newsintel.adapters.extractors.article_html import extract_article_html
from newsintel.core.config import get_settings
from newsintel.domain.intelligence.digest_quality import headline_terms
from newsintel.infrastructure.db.models import ArticleVersionModel
from newsintel.infrastructure.db.session import Database

ROOT = Path(__file__).resolve().parents[1]


async def main():
    evidence = json.loads((ROOT / ".run/audit/reader-freshness-live-20261030.json").read_text(encoding="utf-8"))
    database = Database(get_settings())
    checked = []
    try:
        async with database.session_factory() as session:
            for period in ("daily", "weekly"):
                edition = evidence[period]["edition"]
                end = datetime.fromisoformat(edition["window_end"])
                for item in edition["items"]:
                    row = await session.scalar(select(ArticleVersionModel).where(
                        ArticleVersionModel.article_id == UUID(item["article_id"]),
                        ArticleVersionModel.created_at <= end,
                    ).order_by(ArticleVersionModel.version_number.desc()).limit(1))
                    raw = row.metadata_.get("raw_fetch_artifact") or {}
                    parsed = urlsplit(raw.get("artifact_uri", ""))
                    result = {"period": period, "article_id": str(row.article_id),
                              "version_id": str(row.id), "title": row.title}
                    if parsed.scheme != "file" or parsed.netloc:
                        checked.append(dict(result, status="no_local_snapshot"))
                        continue
                    path = Path(url2pathname(parsed.path)).resolve()
                    if not path.is_relative_to((ROOT / "artifacts").resolve()):
                        raise ValueError("Snapshot lies outside this workspace's artifact store")
                    body = path.read_bytes()
                    assert hashlib.sha256(body).hexdigest() == raw["sha256"]
                    extracted = await asyncio.to_thread(extract_article_html, body, base_url=row.final_url)
                    old, new = headline_terms(row.title), headline_terms(extracted.title or "")
                    similarity = len(old & new) / max(1, len(old | new))
                    same_date = row.published_at == extracted.published_at
                    status = "confirmed" if same_date and similarity >= .75 else "needs_review"
                    checked.append(dict(result, status=status, stored_publication=row.published_at.isoformat(),
                        reextracted_publication=extracted.published_at.isoformat() if extracted.published_at else None,
                        reextracted_title=extracted.title, headline_similarity=round(similarity, 3)))
        (ROOT / ".run/audit/reader-snapshot-dates-20261030.json").write_text(
            json.dumps(checked, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"checked": len(checked), "confirmed": sum(r["status"] == "confirmed" for r in checked),
                          "needs_review": [r for r in checked if r["status"] != "confirmed"]}, ensure_ascii=False))
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
