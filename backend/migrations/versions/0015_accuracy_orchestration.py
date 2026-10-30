"""accuracy benchmarks, evidence orchestration and external entity identifiers

Revision ID: 0015_accuracy_orchestration
Revises: 0014_ownership_entities_calibration
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_accuracy_orchestration"
down_revision: str | None = "0014_ownership_entities_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("verification_benchmark_cases", sa.Column("case_key", sa.String(160)))
    op.add_column("verification_benchmark_cases", sa.Column("split", sa.String(40), server_default="unspecified", nullable=False))
    op.add_column("verification_benchmark_cases", sa.Column("topic_key", sa.String(80)))
    op.add_column("verification_benchmark_cases", sa.Column("language", sa.String(35)))
    op.add_column("verification_benchmark_cases", sa.Column("jurisdiction", sa.String(120)))
    op.add_column("verification_benchmark_cases", sa.Column("adjudicator_count", sa.Integer(), server_default="1", nullable=False))
    op.add_column("verification_benchmark_cases", sa.Column("adjudicated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_verification_benchmark_set_split", "verification_benchmark_cases", ["benchmark_set", "split"])

    op.create_table(
        "evidence_orchestration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_search_runs.id"), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("orchestration_version", sa.String(120), nullable=False),
        sa.Column("required_evidence_classes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("selected_authority_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("uncovered_evidence_classes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("coverage_ratio", sa.Float(), nullable=False),
        sa.Column("status", sa.String(40), server_default="planned", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_orchestration_claim_created", "evidence_orchestration_runs", ["claim_id", "created_at"])
    op.create_index("ix_evidence_orchestration_search_run", "evidence_orchestration_runs", ["search_run_id"])

    op.create_table(
        "claim_conflict_resolutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("resolver_version", sa.String(120), nullable=False),
        sa.Column("state", sa.String(60), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("support_weight", sa.Float(), nullable=False),
        sa.Column("contradiction_weight", sa.Float(), nullable=False),
        sa.Column("dispute_weight", sa.Float(), nullable=False),
        sa.Column("temporal_update_weight", sa.Float(), nullable=False),
        sa.Column("independent_lineage_count", sa.Integer(), nullable=False),
        sa.Column("primary_support", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("primary_contradiction", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_conflict_resolutions_claim_created", "claim_conflict_resolutions", ["claim_id", "created_at"])

    op.create_table(
        "verification_benchmark_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(120), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("effective_weight", sa.Float(), nullable=False),
        sa.Column("accuracy", sa.Float()),
        sa.Column("macro_precision", sa.Float()),
        sa.Column("macro_recall", sa.Float()),
        sa.Column("macro_f1", sa.Float()),
        sa.Column("high_confidence_error_rate", sa.Float()),
        sa.Column("per_label", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("confusion_matrix", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("selective_metrics", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_benchmark_eval_set_created", "verification_benchmark_evaluations", ["benchmark_set", "created_at"])

    op.create_table(
        "entity_external_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("namespace", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("canonical_url", sa.Text()),
        sa.Column("provenance_url", sa.Text()),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "external_id", name="uq_entity_external_namespace_id"),
        sa.UniqueConstraint("entity_id", "namespace", "external_id", name="uq_entity_external_entity_namespace_id"),
    )
    op.create_index("ix_entity_external_entity", "entity_external_identifiers", ["entity_id"])

    op.create_table(
        "ownership_provenance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publisher_ownership_memberships.id"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("passage_text", sa.Text()),
        sa.Column("passage_sha256", sa.String(64)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ownership_provenance_membership_observed", "ownership_provenance_records", ["membership_id", "observed_at"])

    # Existing canonical_entities.external_ids remains a compatibility cache. New links are
    # provenance-preserving rows and can be backfilled by future maintenance tooling.


def downgrade() -> None:
    op.drop_table("ownership_provenance_records")
    op.drop_table("entity_external_identifiers")
    op.drop_table("verification_benchmark_evaluations")
    op.drop_table("claim_conflict_resolutions")
    op.drop_table("evidence_orchestration_runs")
    op.drop_index("ix_verification_benchmark_set_split", table_name="verification_benchmark_cases")
    op.drop_column("verification_benchmark_cases", "adjudicated_at")
    op.drop_column("verification_benchmark_cases", "adjudicator_count")
    op.drop_column("verification_benchmark_cases", "jurisdiction")
    op.drop_column("verification_benchmark_cases", "language")
    op.drop_column("verification_benchmark_cases", "topic_key")
    op.drop_column("verification_benchmark_cases", "split")
    op.drop_column("verification_benchmark_cases", "case_key")
