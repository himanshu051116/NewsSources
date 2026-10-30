"""entity resolution review and benchmark expansion

Revision ID: 0028_entity_resolution_benchmark_expansion
Revises: 0027_search_quality_entity_intelligence
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0028_entity_resolution_benchmark_expansion"
down_revision: str | None = "0027_search_quality_entity_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "canonical_entities",
        sa.Column("resolution_status", sa.String(length=24), nullable=False, server_default="active"),
    )
    op.add_column(
        "canonical_entities",
        sa.Column("merged_into_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_canonical_entities_merged_into",
        "canonical_entities",
        "canonical_entities",
        ["merged_into_entity_id"],
        ["id"],
    )
    op.create_index(
        "ix_canonical_entities_resolution_status",
        "canonical_entities",
        ["resolution_status", "updated_at"],
        unique=False,
    )

    # Actions are created first so candidates can reference a completed resolution action.
    op.create_table(
        "entity_resolution_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alias_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_entity_id"], ["canonical_entities.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["canonical_entities.id"]),
        sa.ForeignKeyConstraint(["new_entity_id"], ["canonical_entities.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_resolution_actions_created", "entity_resolution_actions", ["created_at"], unique=False)

    op.create_table(
        "entity_resolution_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_key", sa.String(length=64), nullable=False),
        sa.Column("candidate_type", sa.String(length=40), nullable=False),
        sa.Column("normalized_value", sa.Text(), nullable=False),
        sa.Column("entity_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("resolved_action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["resolved_action_id"], ["entity_resolution_actions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_key", name="uq_entity_resolution_candidate_key"),
    )
    op.create_index(
        "ix_entity_resolution_candidates_status_created",
        "entity_resolution_candidates",
        ["status", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_entity_resolution_actions_candidate",
        "entity_resolution_actions",
        "entity_resolution_candidates",
        ["candidate_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_entity_resolution_actions_candidate", "entity_resolution_actions", type_="foreignkey")
    op.drop_index("ix_entity_resolution_candidates_status_created", table_name="entity_resolution_candidates")
    op.drop_table("entity_resolution_candidates")
    op.drop_index("ix_entity_resolution_actions_created", table_name="entity_resolution_actions")
    op.drop_table("entity_resolution_actions")
    op.drop_index("ix_canonical_entities_resolution_status", table_name="canonical_entities")
    op.drop_constraint("fk_canonical_entities_merged_into", "canonical_entities", type_="foreignkey")
    op.drop_column("canonical_entities", "merged_into_entity_id")
    op.drop_column("canonical_entities", "resolution_status")
