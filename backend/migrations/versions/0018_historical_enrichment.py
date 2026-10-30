"""automatic historical enrichment for every committed article version

Revision ID: 0018_historical_enrichment
Revises: 0017_production_readiness
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_historical_enrichment"
down_revision: str | None = "0017_production_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_historical_enrichment_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("article_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_versions.id"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(240), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query_terms", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_version_id", name="uq_historical_enrichment_job_version"),
    )
    op.create_index(
        "ix_historical_enrichment_jobs_due",
        "article_historical_enrichment_jobs",
        ["state", "next_attempt_at"],
    )
    op.create_index(
        "ix_historical_enrichment_jobs_article_created",
        "article_historical_enrichment_jobs",
        ["article_id", "created_at"],
    )

    op.create_table(
        "article_historical_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("article_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_versions.id"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queries", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("same_event_history", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("prior_claim_history", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("internal_matches", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("external_matches", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("provider_statuses", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("timeline_summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("context_summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_version_id", name="uq_article_historical_context_version"),
    )
    op.create_index(
        "ix_article_historical_context_article_generated",
        "article_historical_contexts",
        ["article_id", "generated_at"],
    )
    op.create_index(
        "ix_article_historical_context_event_generated",
        "article_historical_contexts",
        ["event_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("article_historical_contexts")
    op.drop_table("article_historical_enrichment_jobs")
