"""adaptive extraction profiles and optional semantic indexing

Revision ID: 0021_adaptive_extraction_semantic
Revises: 0020_coherence_retrieval
Create Date: 2026-08-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0021_adaptive_extraction_semantic"
down_revision: str | None = "0020_coherence_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publisher_extraction_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("preferred_method", sa.String(length=80), nullable=False, server_default="auto"),
        sa.Column("recommended_method", sa.String(length=80), nullable=True),
        sa.Column("low_value_phrases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("skip_attribute_tokens", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("skip_attribute_phrases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("paywall_or_partial_phrases", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("method_stats", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("full_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("partial_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_quality_score", sa.Float(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("publisher_id", name="uq_publisher_extraction_profile_publisher"),
    )
    op.create_index(
        "ix_publisher_extraction_profiles_domain",
        "publisher_extraction_profiles",
        ["domain"],
    )

    op.add_column(
        "article_versions",
        sa.Column("semantic_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "article_versions",
        sa.Column("semantic_model", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "article_versions",
        sa.Column("semantic_content_sha256", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_article_versions_semantic_pending",
        "article_versions",
        ["semantic_indexed_at", "created_at"],
    )



def downgrade() -> None:
    op.drop_index("ix_article_versions_semantic_pending", table_name="article_versions")
    op.drop_column("article_versions", "semantic_content_sha256")
    op.drop_column("article_versions", "semantic_model")
    op.drop_column("article_versions", "semantic_indexed_at")

    op.drop_index(
        "ix_publisher_extraction_profiles_domain",
        table_name="publisher_extraction_profiles",
    )
    op.drop_table("publisher_extraction_profiles")
