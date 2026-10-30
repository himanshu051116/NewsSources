"""verification manifests, dependency propagation, and production readiness

Revision ID: 0017_production_readiness
Revises: 0016_validation_propagation
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_production_readiness"
down_revision: str | None = "0016_validation_propagation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "correction_dependency_propagation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "correction_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("article_correction_events.id"),
            nullable=False,
        ),
        sa.Column("root_article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("correction_kind", sa.String(60), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("direct_dependency_count", sa.Integer(), nullable=False),
        sa.Column("indirect_dependency_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("impacts", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_correction_dependency_event_created",
        "correction_dependency_propagation_runs",
        ["correction_event_id", "created_at"],
    )

    op.create_table(
        "verification_run_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column(
            "verification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claim_verifications.id"),
            nullable=False,
        ),
        sa.Column("manifest_version", sa.String(120), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("code_version", sa.String(40), nullable=False),
        sa.Column("claim_sha256", sa.String(64), nullable=False),
        sa.Column("article_content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("authority_snapshot", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("decision_context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("verification_id", "manifest_version", name="uq_verification_manifest_version"),
        sa.UniqueConstraint("manifest_sha256", name="uq_verification_manifest_sha256"),
    )
    op.create_index(
        "ix_verification_manifest_claim_created",
        "verification_run_manifests",
        ["claim_id", "created_at"],
    )

    op.create_table(
        "production_readiness_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(120), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("failures", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("checks", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_production_readiness_benchmark_created",
        "production_readiness_runs",
        ["benchmark_set", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("production_readiness_runs")
    op.drop_table("verification_run_manifests")
    op.drop_table("correction_dependency_propagation_runs")
