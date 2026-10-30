"""investigation collaboration and durable saved-search monitoring

Revision ID: 0025_collaboration_monitoring
Revises: 0024_analyst_workspace
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025_collaboration_monitoring"
down_revision: str | None = "0024_analyst_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigation_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("access_role", sa.String(length=20), nullable=False),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("investigation_id", "user_id", name="uq_investigation_member_user"),
    )
    op.create_index("ix_investigation_members_user_updated", "investigation_members", ["user_id", "updated_at"])
    op.create_index("ix_investigation_members_investigation_role", "investigation_members", ["investigation_id", "access_role"])

    op.create_table(
        "investigation_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_investigation_activity_investigation_created", "investigation_activity", ["investigation_id", "created_at"])
    op.create_index("ix_investigation_activity_actor_created", "investigation_activity", ["actor_user_id", "created_at"])

    op.create_table(
        "workspace_monitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cadence_minutes", sa.Integer(), nullable=False, server_default="360"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=240), nullable=True),
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "target_type", "target_id", name="uq_workspace_monitor_owner_target"),
    )
    op.create_index("ix_workspace_monitors_due", "workspace_monitors", ["enabled", "next_run_at"])
    op.create_index("ix_workspace_monitors_owner_updated", "workspace_monitors", ["owner_user_id", "updated_at"])

    op.create_table(
        "workspace_monitor_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspace_monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lease_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("new_result_keys", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workspace_monitor_runs_monitor_started", "workspace_monitor_runs", ["monitor_id", "started_at"])

    op.create_table(
        "workspace_generated_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("alert_key", sa.String(length=300), nullable=False),
        sa.Column("alert_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "alert_key", name="uq_workspace_generated_alert_owner_key"),
    )
    op.create_index("ix_workspace_generated_alerts_owner_occurred", "workspace_generated_alerts", ["owner_user_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_workspace_generated_alerts_owner_occurred", table_name="workspace_generated_alerts")
    op.drop_table("workspace_generated_alerts")
    op.drop_index("ix_workspace_monitor_runs_monitor_started", table_name="workspace_monitor_runs")
    op.drop_table("workspace_monitor_runs")
    op.drop_index("ix_workspace_monitors_owner_updated", table_name="workspace_monitors")
    op.drop_index("ix_workspace_monitors_due", table_name="workspace_monitors")
    op.drop_table("workspace_monitors")
    op.drop_index("ix_investigation_activity_actor_created", table_name="investigation_activity")
    op.drop_index("ix_investigation_activity_investigation_created", table_name="investigation_activity")
    op.drop_table("investigation_activity")
    op.drop_index("ix_investigation_members_investigation_role", table_name="investigation_members")
    op.drop_index("ix_investigation_members_user_updated", table_name="investigation_members")
    op.drop_table("investigation_members")
