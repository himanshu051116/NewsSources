"""browser rendering controls and generic derived-artifact recomputation

Revision ID: 0022_browser_recompute
Revises: 0021_adaptive_extraction_semantic
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0022_browser_recompute"
down_revision: str | None = "0021_adaptive_extraction_semantic"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publisher_extraction_profiles",
        sa.Column("browser_render_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "publisher_extraction_profiles",
        sa.Column("browser_allowed_domains", postgresql.JSONB(), nullable=False, server_default="[]"),
    )

    op.create_table(
        "derived_artifact_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_kind", sa.String(length=80), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "artifact_kind", "artifact_id", "source_kind", "source_id",
            name="uq_derived_artifact_dependency",
        ),
    )
    op.create_index(
        "ix_derived_dependency_source",
        "derived_artifact_dependencies",
        ["source_kind", "source_id"],
    )
    op.create_index(
        "ix_derived_dependency_artifact",
        "derived_artifact_dependencies",
        ["artifact_kind", "artifact_id"],
    )

    op.create_table(
        "derived_artifact_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_kind", sa.String(length=80), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stale_reason", sa.String(length=240), nullable=True),
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_recomputed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("artifact_kind", "artifact_id", name="uq_derived_artifact_state"),
    )
    op.create_index(
        "ix_derived_artifact_stale",
        "derived_artifact_states",
        ["stale", "stale_since"],
    )

    op.create_table(
        "derived_recompute_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_kind", sa.String(length=80), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("reason", sa.String(length=240), nullable=False),
        sa.Column("source_kind", sa.String(length=80), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(length=240), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "artifact_kind", "artifact_id", "generation",
            name="uq_derived_recompute_generation",
        ),
    )
    op.create_index(
        "ix_derived_recompute_due",
        "derived_recompute_jobs",
        ["state", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_derived_recompute_due", table_name="derived_recompute_jobs")
    op.drop_table("derived_recompute_jobs")
    op.drop_index("ix_derived_artifact_stale", table_name="derived_artifact_states")
    op.drop_table("derived_artifact_states")
    op.drop_index("ix_derived_dependency_artifact", table_name="derived_artifact_dependencies")
    op.drop_index("ix_derived_dependency_source", table_name="derived_artifact_dependencies")
    op.drop_table("derived_artifact_dependencies")
    op.drop_column("publisher_extraction_profiles", "browser_allowed_domains")
    op.drop_column("publisher_extraction_profiles", "browser_render_enabled")
