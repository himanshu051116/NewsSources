"""Allow chronological article revisions when body hashes repeat.

Revision ID: 0034_article_revision_history
Revises: 0033_grounded_news_explainer

Each article still has a unique version number. A content hash is no longer
globally unique per article because editorial corrections may be reverted.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_article_revision_history"
down_revision: str | None = "0033_grounded_news_explainer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_article_versions_content", "article_versions", type_="unique",
    )
    op.create_index(
        "ix_article_versions_article_content",
        "article_versions",
        ["article_id", "content_sha256"],
        unique=False,
    )


def downgrade() -> None:
    duplicates = op.get_bind().execute(sa.text("""
        SELECT 1 FROM article_versions
        GROUP BY article_id, content_sha256 HAVING count(*) > 1 LIMIT 1
    """)).first()
    if duplicates is not None:
        raise RuntimeError(
            "Cannot reapply old article/body unique constraint without deleting "
            "legitimate correction history. Archive or reconcile revisions first."
        )
    op.drop_index(
        "ix_article_versions_article_content",
        table_name="article_versions",
    )
    op.create_unique_constraint(
        "uq_article_versions_content",
        "article_versions",
        ["article_id", "content_sha256"],
    )
