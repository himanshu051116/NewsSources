"""search stopping, correction propagation, entity registry linking and quality gates

Revision ID: 0016_validation_propagation
Revises: 0015_accuracy_orchestration
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_validation_propagation"
down_revision: str | None = "0015_accuracy_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("verification_benchmark_cases", sa.Column("group_key", sa.String(180)))
    op.add_column("verification_benchmark_cases", sa.Column("source_document_key", sa.String(180)))
    op.create_index(
        "ix_verification_benchmark_set_group",
        "verification_benchmark_cases",
        ["benchmark_set", "group_key"],
    )
    op.create_table(
        "evidence_search_stopping_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_search_runs.id"), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(60), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("covered_evidence_classes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("uncovered_evidence_classes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("independent_lineages", sa.Integer(), nullable=False),
        sa.Column("primary_records", sa.Integer(), nullable=False),
        sa.Column("rounds_completed", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_stopping_claim_created", "evidence_search_stopping_assessments", ["claim_id", "created_at"])
    op.create_index("ix_search_stopping_run_created", "evidence_search_stopping_assessments", ["search_run_id", "created_at"])

    op.create_table(
        "article_correction_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("article_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_versions.id")),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("correction_kind", sa.String(60), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("affected_claim_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("propagation_plan", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_article_correction_article_created", "article_correction_events", ["article_id", "created_at"])
    op.create_index("ix_article_correction_event_created", "article_correction_events", ["event_id", "created_at"])

    op.create_table(
        "claim_review_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("correction_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_correction_events.id"), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("state", sa.String(40), server_default="review_required", nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("actions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_review_claim_state", "claim_review_flags", ["claim_id", "state"])
    op.create_index("ix_claim_review_correction", "claim_review_flags", ["correction_event_id"])

    op.create_table(
        "verification_quality_gate_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(120), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("verification_benchmark_evaluations.id")),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("failures", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("thresholds", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quality_gate_set_created", "verification_quality_gate_runs", ["benchmark_set", "created_at"])

    op.create_table(
        "entity_registry_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("namespace", sa.String(80), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("search_url_template", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(80)),
        sa.Column("jurisdiction", sa.String(120)),
        sa.Column("language", sa.String(35)),
        sa.Column("adapter_type", sa.String(80), server_default="configured_json", nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "name", name="uq_entity_registry_namespace_name"),
    )
    op.create_index("ix_entity_registry_active_namespace", "entity_registry_profiles", ["active", "namespace"])

    op.create_table(
        "entity_registry_link_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("registry_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("entity_registry_profiles.id"), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("selected_external_id", sa.String(300)),
        sa.Column("selected_score", sa.Float()),
        sa.Column("candidates", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("search_url", sa.Text()),
        sa.Column("response_sha256", sa.String(64)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_entity_registry_link_entity_created", "entity_registry_link_runs", ["entity_id", "created_at"])
    op.create_index("ix_entity_registry_link_profile_created", "entity_registry_link_runs", ["registry_profile_id", "created_at"])

    op.create_table(
        "ownership_ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_count", sa.Integer(), nullable=False),
        sa.Column("membership_created_count", sa.Integer(), nullable=False),
        sa.Column("provenance_created_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ownership_ingest_source_created", "ownership_ingest_runs", ["source_name", "created_at"])


def downgrade() -> None:
    op.drop_table("ownership_ingest_runs")
    op.drop_table("entity_registry_link_runs")
    op.drop_table("entity_registry_profiles")
    op.drop_table("verification_quality_gate_runs")
    op.drop_table("claim_review_flags")
    op.drop_table("article_correction_events")
    op.drop_table("evidence_search_stopping_assessments")
    op.drop_index("ix_verification_benchmark_set_group", table_name="verification_benchmark_cases")
    op.drop_column("verification_benchmark_cases", "source_document_key")
    op.drop_column("verification_benchmark_cases", "group_key")

