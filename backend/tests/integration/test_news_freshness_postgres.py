"""Publication evidence and expiry must survive the SQL-to-reader boundary."""
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from test_article_repository_postgres import persistence as _persistence_fixture

from newsintel.application.digests import DigestFilters, DigestRequest, NewsDigestService
from newsintel.core.ids import uuid7
from newsintel.infrastructure.db.models import (
    ArticleModel,
    ArticleVersionModel,
    EventModel,
    UrlCandidateModel,
)

pytestmark = pytest.mark.integration
persistence = _persistence_fixture


@pytest.mark.asyncio
async def test_current_reader_uses_version_dates_and_snapshot_expiry(persistence):
    factory, candidate_id, _ = persistence
    end = datetime.now(UTC).replace(hour=18, minute=0, second=0, microsecond=0) - timedelta(days=1)
    async with factory() as session, session.begin():
        publisher_id = (await session.get(UrlCandidateModel, candidate_id)).publisher_id
        event_id = uuid7()
        session.add(EventModel(id=event_id, slug=event_id.hex, title="Freshness regression",
            lifecycle_status="active", assignment_status="provisional", metadata_={},
            first_detected_at=end, last_material_change_at=end, created_at=end, updated_at=end))
        await session.flush()

        async def add(title, version_date, *, article_date=None, path="news"):
            article_id = uuid7()
            url = f"https://freshness.example/{path}/{article_id}"
            session.add(ArticleModel(id=article_id, event_id=event_id, publisher_id=publisher_id,
                canonical_url=url, normalized_url_hash=hashlib.sha256(url.encode()).digest(),
                title=title, language="en", published_at=article_date,
                first_observed_at=end - timedelta(hours=1),
                created_at=end - timedelta(hours=1), updated_at=end))
            await session.flush()
            session.add(ArticleVersionModel(id=uuid7(), article_id=article_id, version_number=1,
                source_url=url, final_url=url, title=title, language="en", published_at=version_date,
                retrieved_at=end - timedelta(minutes=20), created_at=end - timedelta(minutes=20),
                content_sha256=hashlib.sha256(title.encode()).hexdigest(),
                text_content=f"Officials confirmed that {title.lower()}, with detailed district figures.",
                extraction_method="test", extraction_warnings=[], metadata_={}))
            return article_id

        recent = await add("Government announces new flood relief funding", end - timedelta(hours=2))
        undated = await add("Central bank report has no publication date", None,
                            article_date=end - timedelta(minutes=10))
        old = await add("Old policy was modified today", end - timedelta(days=300), article_date=end)
        future = await add("Tomorrow's government policy", end + timedelta(days=1))
        archive = await add("From the archives: Previous flood response", end - timedelta(hours=2), path="archives")
        expired = await add("Cyclone live updates: Emergency shelters open", end - timedelta(days=2))
    service = NewsDigestService(factory)
    filters = DigestFilters(publisher_ids=[publisher_id])
    daily = await service.edition(DigestRequest(filters=filters, as_of=end))
    assert {item.article_id for item in daily.items} == {recent}
    assert daily.excluded_stale_or_uncertain == 2
    full = await service.edition(DigestRequest(period="weekly", filters=filters, as_of=end, full_stream=True))
    by_id = {item.article_id: item for item in full.items}
    assert old not in by_id and future not in by_id
    assert by_id[undated].date_basis == "first_captured"
    assert by_id[undated].freshness_status == "date_unconfirmed"
    assert by_id[archive].freshness_status == "historical"
    assert by_id[expired].freshness_status == "expired"
    assert full.excluded_stale_or_uncertain == 3
    latest = await service.edition(DigestRequest(period="weekly", filters=filters, as_of=end,
                                                full_stream=True, current_only=True, page_size=1))
    assert [item.article_id for item in latest.items] == [recent]
    assert latest.next_offset is None and latest.story_count == 1
