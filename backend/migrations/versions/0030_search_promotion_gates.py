"""search promotion gates and semantic coverage readiness

Revision ID: 0030_search_promotion_gates
Revises: 0029_multilingual_reranking_experiments
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0030_search_promotion_gates"
down_revision: str | None = "0029_multilingual_reranking_experiments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_promotion_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("required_languages", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("required_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["platform_users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("benchmark_set", name="uq_search_promotion_policy_benchmark_set"),
    )
    op.create_index("ix_search_promotion_policies_updated", "search_promotion_policies", ["updated_at"], unique=False)

    op.create_table(
        "search_promotion_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("lexical_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hybrid_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("benchmark_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("failures", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("semantic_coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("methodology_version", sa.String(length=100), nullable=False),
        sa.Column("interpretation", sa.Text(), nullable=False),
        sa.Column("evaluated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["search_promotion_policies.id"]),
        sa.ForeignKeyConstraint(["lexical_run_id"], ["search_benchmark_runs.id"]),
        sa.ForeignKeyConstraint(["hybrid_run_id"], ["search_benchmark_runs.id"]),
        sa.ForeignKeyConstraint(["evaluated_by_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_promotion_evaluations_set_created",
        "search_promotion_evaluations",
        ["benchmark_set", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_search_promotion_evaluations_policy_created",
        "search_promotion_evaluations",
        ["policy_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "search_promotion_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_id"], ["search_promotion_evaluations.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_promotion_decisions_evaluation_created",
        "search_promotion_decisions",
        ["evaluation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_search_promotion_decisions_evaluation_created", table_name="search_promotion_decisions")
    op.drop_table("search_promotion_decisions")
    op.drop_index("ix_search_promotion_evaluations_policy_created", table_name="search_promotion_evaluations")
    op.drop_index("ix_search_promotion_evaluations_set_created", table_name="search_promotion_evaluations")
    op.drop_table("search_promotion_evaluations")
    op.drop_index("ix_search_promotion_policies_updated", table_name="search_promotion_policies")
    op.drop_table("search_promotion_policies")
