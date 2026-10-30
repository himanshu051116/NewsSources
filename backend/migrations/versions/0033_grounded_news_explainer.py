"""grounded news explainer

Revision ID: 0033_grounded_news_explainer
Revises: 0032_live_pipeline_hardening
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0033_grounded_news_explainer"
down_revision: str | None = "0032_live_pipeline_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_briefing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("trigger_article_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_versions.id"), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=240)),
        sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_event_briefing_job_event"),
    )
    op.create_index("ix_event_briefing_jobs_due", "event_briefing_jobs", ["state", "next_attempt_at"])

    op.create_table(
        "event_briefings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("trigger_article_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_versions.id"), nullable=False),
        sa.Column("methodology_version", sa.String(length=120), nullable=False),
        sa.Column("evidence_pack_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "evidence_pack_sha256", name="uq_event_briefing_evidence_pack"),
    )
    op.create_index("ix_event_briefings_event_generated", "event_briefings", ["event_id", "generated_at"])


def downgrade() -> None:
    op.drop_index("ix_event_briefings_event_generated", table_name="event_briefings")
    op.drop_table("event_briefings")
    op.drop_index("ix_event_briefing_jobs_due", table_name="event_briefing_jobs")
    op.drop_table("event_briefing_jobs")
