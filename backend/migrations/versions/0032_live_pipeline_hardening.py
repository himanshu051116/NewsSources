"""live acquisition lineage, fenced leases, and article identity foundation

Revision ID: 0032_live_pipeline_hardening
Revises: 0031_search_deployment_control
Create Date: 2026-10-12
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0032_live_pipeline_hardening"
down_revision: str | None = "0031_search_deployment_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("discovery_channels", sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("discovery_channels", sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("discovery_channels", sa.Column("fetch_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_discovery_channels_fetch_job", "discovery_channels", "fetch_jobs", ["fetch_job_id"], ["id"])
    op.create_index("ix_discovery_channels_fetch_job", "discovery_channels", ["fetch_job_id", "active"], unique=False)

    op.add_column("url_candidates", sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("url_candidates", sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("url_candidates", sa.Column("originating_fetch_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_url_candidates_fetch_job", "url_candidates", "fetch_jobs", ["originating_fetch_job_id"], ["id"])
    op.create_index("ix_url_candidates_fetch_job_state", "url_candidates", ["originating_fetch_job_id", "state"], unique=False)

    op.add_column("url_discoveries", sa.Column("fetch_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_url_discoveries_fetch_job", "url_discoveries", "fetch_jobs", ["fetch_job_id"], ["id"])
    op.create_index("ix_url_discoveries_fetch_job_discovered", "url_discoveries", ["fetch_job_id", "discovered_at"], unique=False)

    op.add_column("channel_poll_runs", sa.Column("fetch_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("channel_poll_runs", sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_foreign_key("fk_channel_poll_runs_fetch_job", "channel_poll_runs", "fetch_jobs", ["fetch_job_id"], ["id"])
    op.create_index("ix_channel_poll_runs_fetch_job_started", "channel_poll_runs", ["fetch_job_id", "started_at"], unique=False)

    op.add_column("article_fetch_runs", sa.Column("fetch_job_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("article_fetch_runs", sa.Column("lease_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_foreign_key("fk_article_fetch_runs_fetch_job", "article_fetch_runs", "fetch_jobs", ["fetch_job_id"], ["id"])
    op.create_index("ix_article_fetch_runs_fetch_job_started", "article_fetch_runs", ["fetch_job_id", "started_at"], unique=False)

    op.create_table(
        "fetch_job_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fetch_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_created", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fetch_job_id"], ["fetch_jobs.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["url_candidates.id"]),
        sa.ForeignKeyConstraint(["channel_id"], ["discovery_channels.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fetch_job_id", "candidate_id", "channel_id", name="uq_fetch_job_observation"),
    )
    op.create_index("ix_fetch_job_observations_job_created", "fetch_job_observations", ["fetch_job_id", "candidate_created", "observed_at"], unique=False)

    op.create_table(
        "article_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("representative_article_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["representative_article_id"], ["articles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_key", name="uq_article_identities_key"),
    )
    op.create_index("ix_article_identities_last_observed", "article_identities", ["last_observed_at"], unique=False)

    op.create_table(
        "article_identity_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publisher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_basis", sa.String(length=40), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["identity_id"], ["article_identities.id"]),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"]),
        sa.ForeignKeyConstraint(["publisher_id"], ["publishers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", name="uq_article_identity_member_article"),
    )
    op.create_index("ix_article_identity_members_identity", "article_identity_members", ["identity_id", "created_at"], unique=False)
    op.create_index("ix_article_identity_members_content", "article_identity_members", ["content_sha256"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_article_identity_members_content", table_name="article_identity_members")
    op.drop_index("ix_article_identity_members_identity", table_name="article_identity_members")
    op.drop_table("article_identity_members")
    op.drop_index("ix_article_identities_last_observed", table_name="article_identities")
    op.drop_table("article_identities")

    op.drop_index("ix_fetch_job_observations_job_created", table_name="fetch_job_observations")
    op.drop_table("fetch_job_observations")

    op.drop_index("ix_article_fetch_runs_fetch_job_started", table_name="article_fetch_runs")
    op.drop_constraint("fk_article_fetch_runs_fetch_job", "article_fetch_runs", type_="foreignkey")
    op.drop_column("article_fetch_runs", "lease_version")
    op.drop_column("article_fetch_runs", "fetch_job_id")

    op.drop_index("ix_channel_poll_runs_fetch_job_started", table_name="channel_poll_runs")
    op.drop_constraint("fk_channel_poll_runs_fetch_job", "channel_poll_runs", type_="foreignkey")
    op.drop_column("channel_poll_runs", "lease_version")
    op.drop_column("channel_poll_runs", "fetch_job_id")

    op.drop_index("ix_url_discoveries_fetch_job_discovered", table_name="url_discoveries")
    op.drop_constraint("fk_url_discoveries_fetch_job", "url_discoveries", type_="foreignkey")
    op.drop_column("url_discoveries", "fetch_job_id")

    op.drop_index("ix_url_candidates_fetch_job_state", table_name="url_candidates")
    op.drop_constraint("fk_url_candidates_fetch_job", "url_candidates", type_="foreignkey")
    op.drop_column("url_candidates", "originating_fetch_job_id")
    op.drop_column("url_candidates", "lease_heartbeat_at")
    op.drop_column("url_candidates", "lease_version")

    op.drop_index("ix_discovery_channels_fetch_job", table_name="discovery_channels")
    op.drop_constraint("fk_discovery_channels_fetch_job", "discovery_channels", type_="foreignkey")
    op.drop_column("discovery_channels", "fetch_job_id")
    op.drop_column("discovery_channels", "lease_heartbeat_at")
    op.drop_column("discovery_channels", "lease_version")
