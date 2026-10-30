"""multilingual lexical retrieval and controlled reranking support

Revision ID: 0029_multilingual_reranking_experiments
Revises: 0028_entity_resolution_benchmark_expansion
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_multilingual_reranking_experiments"
down_revision: str | None = "0028_entity_resolution_benchmark_expansion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the language-neutral `simple` indexes from v1.17. These additional
    # English vectors are a morphology fallback for Latin/English queries; Hindi
    # and other scripts continue to use the simple configuration.
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_article_versions_search_english_fts
            ON article_versions
            USING GIN (
                (
                    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(byline, '')), 'B') ||
                    setweight(to_tsvector('english', coalesce(text_content, '')), 'C')
                )
            )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_article_claims_search_english_fts
            ON article_claims
            USING GIN (to_tsvector('english', coalesce(claim_text, '')))
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_search_english_fts
            ON events
            USING GIN (to_tsvector('english', coalesce(title, '')))
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_events_search_english_fts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_article_claims_search_english_fts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_article_versions_search_english_fts")
