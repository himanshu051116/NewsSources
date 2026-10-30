"""executable evidence retrieval, temporal graph and publisher reliability

Revision ID: 0013_evidence_graph_reliability
Revises: 0012_evidence_temporal_knowledge
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_evidence_graph_reliability"
down_revision: str | None = "0012_evidence_temporal_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_authority_profiles",
        sa.Column(
            "adapter_type",
            sa.String(60),
            server_default="generic_html_search",
            nullable=False,
        ),
    )

    op.create_table(
        "evidence_retrieval_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "search_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_search_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "authority_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evidence_authority_profiles.id"),
            nullable=False,
        ),
        sa.Column("search_url", sa.Text()),
        sa.Column("candidate_url", sa.Text()),
        sa.Column("status", sa.String(60), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("body_sha256", sa.String(64)),
        sa.Column("error_type", sa.String(160)),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_evidence_retrieval_attempts_run_created",
        "evidence_retrieval_attempts",
        ["search_run_id", "created_at"],
    )
    op.create_index(
        "ix_evidence_retrieval_attempts_authority_created",
        "evidence_retrieval_attempts",
        ["authority_profile_id", "created_at"],
    )

    op.create_table(
        "publisher_reliability_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
            nullable=False,
        ),
        sa.Column("topic_key", sa.String(80), nullable=False),
        sa.Column("methodology_version", sa.String(120), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posterior_mean", sa.Float()),
        sa.Column("interval_low", sa.Float()),
        sa.Column("interval_high", sa.Float()),
        sa.Column("effective_successes", sa.Float(), server_default="0", nullable=False),
        sa.Column("effective_failures", sa.Float(), server_default="0", nullable=False),
        sa.Column("effective_sample_size", sa.Float(), server_default="0", nullable=False),
        sa.Column("raw_observation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("excluded_observation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("prior_alpha", sa.Float(), nullable=False),
        sa.Column("prior_beta", sa.Float(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_publisher_reliability_scope_window",
        "publisher_reliability_snapshots",
        ["publisher_id", "topic_key", "window_end"],
    )

    op.create_table(
        "temporal_knowledge_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.Column("node_key", sa.String(120), nullable=False),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("graph_version", sa.String(120), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "node_key", name="uq_temporal_knowledge_event_node"),
    )
    op.create_index(
        "ix_temporal_knowledge_nodes_event_observed",
        "temporal_knowledge_nodes",
        ["event_id", "observed_at"],
    )

    op.create_table(
        "temporal_knowledge_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("events.id"),
            nullable=False,
        ),
        sa.Column("edge_key", sa.String(64), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("target_key", sa.String(120), nullable=False),
        sa.Column("relation", sa.String(60), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("graph_version", sa.String(120), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "edge_key", name="uq_temporal_knowledge_event_edge"),
    )
    op.create_index(
        "ix_temporal_knowledge_edges_event_observed",
        "temporal_knowledge_edges",
        ["event_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_table("temporal_knowledge_edges")
    op.drop_table("temporal_knowledge_nodes")
    op.drop_table("publisher_reliability_snapshots")
    op.drop_table("evidence_retrieval_attempts")
    op.drop_column("evidence_authority_profiles", "adapter_type")
