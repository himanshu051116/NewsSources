"""search quality benchmarking and entity intelligence

Revision ID: 0027_search_quality_entity_intelligence
Revises: 0026_search_infrastructure
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0027_search_quality_entity_intelligence"
down_revision: str | None = "0026_search_infrastructure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_benchmark_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("case_key", sa.String(length=64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("result_type", sa.String(length=20), nullable=False, server_default="all"),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("language", sa.String(length=35), nullable=True),
        sa.Column("topic_key", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("benchmark_set", "case_key", name="uq_search_benchmark_set_case"),
    )
    op.create_index(
        "ix_search_benchmark_queries_set_created",
        "search_benchmark_queries",
        ["benchmark_set", "created_at"],
        unique=False,
    )
    op.create_table(
        "search_relevance_judgments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_type", sa.String(length=20), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relevance_grade", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("adjudicator_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["search_benchmark_queries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["adjudicator_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query_id", "result_type", "result_id", name="uq_search_judgment_query_result"),
    )
    op.create_index(
        "ix_search_relevance_query_grade",
        "search_relevance_judgments",
        ["query_id", "relevance_grade"],
        unique=False,
    )
    op.create_table(
        "search_benchmark_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("search_mode", sa.String(length=80), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column("judged_query_count", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("latency", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_benchmark_runs_set_created",
        "search_benchmark_runs",
        ["benchmark_set", "created_at"],
        unique=False,
    )
    op.create_table(
        "search_query_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_type", sa.String(length=20), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("include_claims", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("returned_count", sa.Integer(), nullable=False),
        sa.Column("cursor_page", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_query_observations_created",
        "search_query_observations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_search_query_observations_fingerprint_created",
        "search_query_observations",
        ["query_fingerprint", "created_at"],
        unique=False,
    )
    op.create_table(
        "entity_mentions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mention_text", sa.Text(), nullable=False),
        sa.Column("normalized_mention", sa.Text(), nullable=False),
        sa.Column("link_basis", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["canonical_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_version_id"], ["article_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["article_claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entity_id", "claim_id", "normalized_mention", name="uq_entity_mention_claim_text"),
    )
    op.create_index(
        "ix_entity_mentions_entity_created",
        "entity_mentions",
        ["entity_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_entity_mentions_claim",
        "entity_mentions",
        ["claim_id"],
        unique=False,
    )

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_canonical_entities_search_fts
            ON canonical_entities
            USING GIN (to_tsvector('simple', coalesce(canonical_name, '')))
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_entity_aliases_search_fts
            ON entity_aliases
            USING GIN (to_tsvector('simple', coalesce(alias, '')))
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_entity_aliases_search_fts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_canonical_entities_search_fts")
    op.drop_index("ix_entity_mentions_claim", table_name="entity_mentions")
    op.drop_index("ix_entity_mentions_entity_created", table_name="entity_mentions")
    op.drop_table("entity_mentions")
    op.drop_index("ix_search_query_observations_fingerprint_created", table_name="search_query_observations")
    op.drop_index("ix_search_query_observations_created", table_name="search_query_observations")
    op.drop_table("search_query_observations")
    op.drop_index("ix_search_benchmark_runs_set_created", table_name="search_benchmark_runs")
    op.drop_table("search_benchmark_runs")
    op.drop_index("ix_search_relevance_query_grade", table_name="search_relevance_judgments")
    op.drop_table("search_relevance_judgments")
    op.drop_index("ix_search_benchmark_queries_set_created", table_name="search_benchmark_queries")
    op.drop_table("search_benchmark_queries")
