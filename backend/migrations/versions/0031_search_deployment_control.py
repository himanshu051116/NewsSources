"""production search deployment control and canary telemetry

Revision ID: 0031_search_deployment_control
Revises: 0030_search_promotion_gates
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0031_search_deployment_control"
down_revision: str | None = "0030_search_promotion_gates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("target_percent", sa.Float(), nullable=False),
        sa.Column("promotion_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("benchmark_set", sa.String(length=120), nullable=True),
        sa.Column("rollout_salt", sa.String(length=80), nullable=False),
        sa.Column("max_hybrid_p95_ms", sa.Float(), nullable=False),
        sa.Column("max_hybrid_error_rate", sa.Float(), nullable=False),
        sa.Column("min_hybrid_samples", sa.Integer(), nullable=False),
        sa.Column("circuit_window_minutes", sa.Integer(), nullable=False),
        sa.Column("auto_pause", sa.Boolean(), nullable=False),
        sa.Column("configured_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["promotion_decision_id"], ["search_promotion_decisions.id"]),
        sa.ForeignKeyConstraint(["configured_by_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_search_deployments_name"),
    )
    op.create_index("ix_search_deployments_state_updated", "search_deployments", ["state", "updated_at"], unique=False)

    op.create_table(
        "search_deployment_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_bucket", sa.Integer(), nullable=False),
        sa.Column("assigned_variant", sa.String(length=24), nullable=False),
        sa.Column("served_variant", sa.String(length=24), nullable=False),
        sa.Column("query_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("subject_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("result_type", sa.String(length=20), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("fallback_reason", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["search_deployments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_deployment_obs_deployment_created",
        "search_deployment_observations",
        ["deployment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_search_deployment_obs_variant_created",
        "search_deployment_observations",
        ["served_variant", "created_at"],
        unique=False,
    )

    op.create_table(
        "search_deployment_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("result_type", sa.String(length=20), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["observation_id"], ["search_deployment_observations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", "action", "result_type", "result_id", name="uq_search_deployment_outcome"),
    )
    op.create_index(
        "ix_search_deployment_outcomes_observation_created",
        "search_deployment_outcomes",
        ["observation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "search_deployment_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("previous_state", sa.String(length=24), nullable=False),
        sa.Column("new_state", sa.String(length=24), nullable=False),
        sa.Column("target_percent", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["search_deployments.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["platform_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_deployment_actions_deployment_created",
        "search_deployment_actions",
        ["deployment_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_search_deployment_actions_deployment_created", table_name="search_deployment_actions")
    op.drop_table("search_deployment_actions")
    op.drop_index("ix_search_deployment_outcomes_observation_created", table_name="search_deployment_outcomes")
    op.drop_table("search_deployment_outcomes")
    op.drop_index("ix_search_deployment_obs_variant_created", table_name="search_deployment_observations")
    op.drop_index("ix_search_deployment_obs_deployment_created", table_name="search_deployment_observations")
    op.drop_table("search_deployment_observations")
    op.drop_index("ix_search_deployments_state_updated", table_name="search_deployments")
    op.drop_table("search_deployments")
