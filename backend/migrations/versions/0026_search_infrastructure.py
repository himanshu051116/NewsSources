"""ranked full-text search infrastructure

Revision ID: 0026_search_infrastructure
Revises: 0025_collaboration_monitoring
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_search_infrastructure"
down_revision: str | None = "0025_collaboration_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Index builds are intentionally concurrent. The existing unweighted
    # article_versions FTS index remains available to historical retrieval;
    # v1.17 adds a separate weighted index for interactive corpus search.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_article_versions_search_weighted_fts
            ON article_versions
            USING GIN (
                (
                    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(byline, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(text_content, '')), 'C')
                )
            )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_search_fts
            ON events
            USING GIN (to_tsvector('simple', coalesce(title, '')))
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_article_claims_search_fts
            ON article_claims
            USING GIN (to_tsvector('simple', coalesce(claim_text, '')))
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_lifecycle_changed
            ON events (lifecycle_status, last_material_change_at DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_articles_language_published
            ON articles (language, published_at DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_articles_publisher_published
            ON articles (publisher_id, published_at DESC)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_articles_publisher_published")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_articles_language_published")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_events_lifecycle_changed")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_article_claims_search_fts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_events_search_fts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_article_versions_search_weighted_fts")
