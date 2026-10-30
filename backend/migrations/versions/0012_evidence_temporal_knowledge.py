"""primary evidence, temporal stance and outcome tracking

Revision ID: 0012_evidence_temporal_knowledge
Revises: 0011_source_fabric_registry
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_evidence_temporal_knowledge"
down_revision: str | None = "0011_source_fabric_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_authority_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("evidence_class", sa.String(80), nullable=False),
        sa.Column("jurisdiction", sa.String(120), nullable=False),
        sa.Column("language", sa.String(35)),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("allowed_domains", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("search_url_template", sa.Text()),
        sa.Column("trust_scope", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "jurisdiction", "evidence_class", name="uq_evidence_authority_scope"),
    )
    op.create_index("ix_evidence_authority_class_active", "evidence_authority_profiles", ["evidence_class", "active"])

    op.create_table(
        "evidence_search_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("plan_key", sa.String(64), nullable=False),
        sa.Column("planner_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("plan", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("retrieval_complete", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_search_runs_claim_created", "evidence_search_runs", ["claim_id", "created_at"])
    op.create_index("ix_evidence_search_runs_status_created", "evidence_search_runs", ["status", "created_at"])

    op.create_table(
        "evidence_passage_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("search_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_search_runs.id")),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("evidence_class", sa.String(80)),
        sa.Column("passage_text", sa.Text(), nullable=False),
        sa.Column("passage_sha256", sa.String(64), nullable=False),
        sa.Column("stance", sa.String(40), nullable=False),
        sa.Column("stance_confidence", sa.Float(), nullable=False),
        sa.Column("assessor_version", sa.String(100), nullable=False),
        sa.Column("temporal_relation", sa.String(60), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("independence_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("primary_source", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("claim_id", "source_url", "passage_sha256", name="uq_evidence_passage_claim_source_hash"),
    )
    op.create_index("ix_evidence_passage_eval_claim_retrieved", "evidence_passage_evaluations", ["claim_id", "retrieved_at"])
    op.create_index("ix_evidence_passage_eval_run", "evidence_passage_evaluations", ["search_run_id"])

    op.create_table(
        "event_commitments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("source_claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id"), nullable=False),
        sa.Column("commitment_key", sa.String(64), nullable=False),
        sa.Column("commitment_type", sa.String(40), nullable=False),
        sa.Column("commitment_text", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text()),
        sa.Column("deadline_text", sa.Text()),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "commitment_key", name="uq_event_commitment_key"),
    )
    op.create_index("ix_event_commitments_event_status", "event_commitments", ["event_id", "status"])

    op.create_table(
        "commitment_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("commitment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("event_commitments.id"), nullable=False),
        sa.Column("source_claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id")),
        sa.Column("evidence_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("tracker_version", sa.String(100), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commitment_outcomes_commitment_observed", "commitment_outcomes", ["commitment_id", "observed_at"])


def downgrade() -> None:
    op.drop_table("commitment_outcomes")
    op.drop_table("event_commitments")
    op.drop_table("evidence_passage_evaluations")
    op.drop_table("evidence_search_runs")
    op.drop_table("evidence_authority_profiles")
