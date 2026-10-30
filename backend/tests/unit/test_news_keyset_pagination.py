"""Regression coverage for stable article feed continuation under new ingestion."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from newsintel.application.articles.query_service import ArticleQueryService


class _Result:
    def all(self):
        return []


class _Session:
    def __init__(self):
        self.statements = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalars(self, statement):
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return _Result()


@pytest.mark.asyncio
async def test_article_feed_keyset_cursor_has_stable_total_ordering():
    session = _Session()
    service = ArticleQueryService(lambda: session)
    at = datetime(2026, 10, 13, tzinfo=UTC)
    await service.list_articles(limit=5, before_observed_at=at, before_id=uuid4())
    assert session.statements
    sql = session.statements[0]
    assert 'articles.first_observed_at <' in sql
    assert 'articles.id <' in sql
    assert 'articles.first_observed_at DESC, articles.id DESC' in sql
    assert 'OFFSET' not in sql


@pytest.mark.asyncio
async def test_article_feed_rejects_partial_or_ambiguous_cursor():
    service = ArticleQueryService(lambda: _Session())
    with pytest.raises(ValueError, match='supplied together'):
        await service.list_articles(before_id=uuid4())
    with pytest.raises(ValueError, match='timezone'):
        await service.list_articles(before_observed_at=datetime(2026, 10, 13), before_id=uuid4())
    with pytest.raises(ValueError, match='cannot be mixed'):
        await service.list_articles(before_observed_at=datetime(2026, 10, 13, tzinfo=UTC), before_id=uuid4(), offset=2)
