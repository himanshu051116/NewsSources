"""blind adjudication workflow and accuracy diagnostics

Revision ID: 0023_blind_adjudication_diagnostics
Revises: 0022_browser_recompute
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023_blind_adjudication_diagnostics"
down_revision: str | None = "0022_browser_recompute"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "verification_benchmark_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("case_key", sa.String(length=160), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=True),
        sa.Column("group_key", sa.String(length=180), nullable=True),
        sa.Column("source_document_key", sa.String(length=180), nullable=True),
        sa.Column("split", sa.String(length=40), nullable=False, server_default="test"),
        sa.Column("topic_key", sa.String(length=80), nullable=True),
        sa.Column("language", sa.String(length=35), nullable=True),
        sa.Column("jurisdiction", sa.String(length=120), nullable=True),
        sa.Column("predicted_label", sa.String(length=40), nullable=False),
        sa.Column("predicted_confidence", sa.Float(), nullable=False),
        sa.Column("prediction_methodology", sa.String(length=120), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="sampled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("benchmark_set", "case_key", name="uq_verification_benchmark_candidate_case"),
    )
    op.create_index("ix_verification_candidate_set_status", "verification_benchmark_candidates", ["benchmark_set", "status"])
    op.create_index("ix_verification_candidate_claim", "verification_benchmark_candidates", ["claim_id"])

    op.create_table(
        "verification_benchmark_adjudications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_benchmark_candidates.id"), nullable=False),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("case_key", sa.String(length=160), nullable=False),
        sa.Column("reviewer_key_hash", sa.String(length=64), nullable=False),
        sa.Column("reviewer_role", sa.String(length=30), nullable=False, server_default="reviewer"),
        sa.Column("adjudicated_label", sa.String(length=40), nullable=False),
        sa.Column("adjudication_source", sa.String(length=300), nullable=False),
        sa.Column("adjudication_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("candidate_id", "reviewer_key_hash", name="uq_verification_adjudication_reviewer"),
    )
    op.create_index("ix_verification_adjudication_set_case", "verification_benchmark_adjudications", ["benchmark_set", "case_key"])
    op.create_index("ix_verification_adjudication_candidate", "verification_benchmark_adjudications", ["candidate_id"])

    op.create_table(
        "verification_benchmark_agreement_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("methodology_version", sa.String(length=120), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("multi_review_case_count", sa.Integer(), nullable=False),
        sa.Column("unanimous_case_count", sa.Integer(), nullable=False),
        sa.Column("disagreement_case_count", sa.Integer(), nullable=False),
        sa.Column("pairwise_agreement", sa.Float(), nullable=True),
        sa.Column("krippendorff_alpha_nominal", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_agreement_set_created", "verification_benchmark_agreement_snapshots", ["benchmark_set", "created_at"])

    op.create_table(
        "verification_benchmark_diagnostic_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(length=120), nullable=False),
        sa.Column("methodology_version", sa.String(length=120), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("taxonomy_counts", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("slice_metrics", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_diagnostic_set_created", "verification_benchmark_diagnostic_runs", ["benchmark_set", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_verification_diagnostic_set_created", table_name="verification_benchmark_diagnostic_runs")
    op.drop_table("verification_benchmark_diagnostic_runs")
    op.drop_index("ix_verification_agreement_set_created", table_name="verification_benchmark_agreement_snapshots")
    op.drop_table("verification_benchmark_agreement_snapshots")
    op.drop_index("ix_verification_adjudication_candidate", table_name="verification_benchmark_adjudications")
    op.drop_index("ix_verification_adjudication_set_case", table_name="verification_benchmark_adjudications")
    op.drop_table("verification_benchmark_adjudications")
    op.drop_index("ix_verification_candidate_claim", table_name="verification_benchmark_candidates")
    op.drop_index("ix_verification_candidate_set_status", table_name="verification_benchmark_candidates")
    op.drop_table("verification_benchmark_candidates")
