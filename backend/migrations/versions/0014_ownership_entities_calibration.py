"""ownership-aware lineage, canonical entities and confidence calibration

Revision ID: 0014_ownership_entities_calibration
Revises: 0013_evidence_graph_reliability
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_ownership_entities_calibration"
down_revision: str | None = "0013_evidence_graph_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # This is the first revision whose identifier exceeds Alembic's default
    # VARCHAR(32). Widen before Alembic records it, including on a clean install.
    # Keep the wider metadata column on downgrade so long revisions remain usable.
    op.alter_column(
        "alembic_version", "version_num", existing_type=sa.String(32), type_=sa.String(128)
    )
    op.add_column(
        "evidence_authority_profiles",
        sa.Column(
            "adapter_config",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "temporal_knowledge_nodes",
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
    )
    op.execute("UPDATE temporal_knowledge_nodes SET search_text = lower(label)")
    op.create_index(
        "ix_temporal_knowledge_nodes_search_fts",
        "temporal_knowledge_nodes",
        [sa.text("to_tsvector('simple', search_text)")],
        postgresql_using="gin",
    )

    op.create_table(
        "media_ownership_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("canonical_domain", sa.String(253)),
        sa.Column("jurisdiction", sa.String(120)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_media_ownership_groups_name"),
    )
    op.create_table(
        "publisher_ownership_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("publisher_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("publishers.id"), nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media_ownership_groups.id"), nullable=False),
        sa.Column("relationship", sa.String(60), nullable=False),
        sa.Column("ownership_fraction", sa.Float()),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("provenance_url", sa.Text()),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publisher_ownership_publisher_valid", "publisher_ownership_memberships", ["publisher_id", "valid_from", "valid_to"])
    op.create_index("ix_publisher_ownership_group_valid", "publisher_ownership_memberships", ["group_id", "valid_from", "valid_to"])

    op.create_table(
        "canonical_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_key", sa.String(64), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("country_code", sa.String(8)),
        sa.Column("external_ids", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity_key", name="uq_canonical_entities_key"),
    )
    op.create_index("ix_canonical_entities_normalized_type", "canonical_entities", ["normalized_name", "entity_type"])
    op.create_table(
        "entity_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("canonical_entities.id"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized_alias", sa.Text(), nullable=False),
        sa.Column("language", sa.String(35)),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity_id", "normalized_alias", name="uq_entity_alias_normalized"),
    )
    op.create_index("ix_entity_alias_lookup", "entity_aliases", ["normalized_alias"])

    op.create_table(
        "verification_benchmark_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("article_claims.id")),
        sa.Column("benchmark_set", sa.String(120), nullable=False),
        sa.Column("predicted_label", sa.String(40), nullable=False),
        sa.Column("predicted_confidence", sa.Float(), nullable=False),
        sa.Column("adjudicated_label", sa.String(40), nullable=False),
        sa.Column("adjudication_source", sa.String(200), nullable=False),
        sa.Column("weight", sa.Float(), server_default="1", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_benchmark_set_created", "verification_benchmark_cases", ["benchmark_set", "created_at"])
    op.create_index("ix_verification_benchmark_claim", "verification_benchmark_cases", ["claim_id"])
    op.create_table(
        "verification_calibration_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("benchmark_set", sa.String(120), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("effective_weight", sa.Float(), nullable=False),
        sa.Column("brier_score", sa.Float()),
        sa.Column("expected_calibration_error", sa.Float()),
        sa.Column("mean_confidence", sa.Float()),
        sa.Column("empirical_accuracy", sa.Float()),
        sa.Column("bins", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_verification_calibration_set_created", "verification_calibration_snapshots", ["benchmark_set", "created_at"])


def downgrade() -> None:
    op.drop_table("verification_calibration_snapshots")
    op.drop_table("verification_benchmark_cases")
    op.drop_table("entity_aliases")
    op.drop_table("canonical_entities")
    op.drop_table("publisher_ownership_memberships")
    op.drop_table("media_ownership_groups")
    op.drop_index("ix_temporal_knowledge_nodes_search_fts", table_name="temporal_knowledge_nodes")
    op.drop_column("temporal_knowledge_nodes", "search_text")
    op.drop_column("evidence_authority_profiles", "adapter_config")
