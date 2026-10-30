"""coherence release retrieval indexes

Revision ID: 0020_coherence_retrieval
Revises: 0019_historical_context_quality
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020_coherence_retrieval"
down_revision: str | None = "0019_historical_context_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_article_versions_fts_simple
        ON article_versions
        USING GIN (
            to_tsvector(
                'simple',
                coalesce(title, '') || ' ' || coalesce(text_content, '')
            )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_article_claims_family_created
        ON article_claims ((extraction_features ->> 'claim_family_key'), created_at DESC)
        WHERE extraction_features ? 'claim_family_key'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_article_claims_family_created")
    op.execute("DROP INDEX IF EXISTS ix_article_versions_fts_simple")
