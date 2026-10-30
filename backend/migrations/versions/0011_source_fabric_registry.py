"""source fabric publisher registry and policy provenance

Revision ID: 0011_source_fabric_registry
Revises: 0010_access_control
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_source_fabric_registry"
down_revision: str | None = "0010_access_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "publisher_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("homepage_url", sa.Text()),
        sa.Column("edition_name", sa.String(200)),
        sa.Column("language", sa.String(35)),
        sa.Column("region", sa.String(100)),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("discovered_via", sa.String(80), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("domain", name="uq_publisher_domains_domain"),
        sa.UniqueConstraint(
            "publisher_id",
            "domain",
            name="uq_publisher_domains_publisher_domain",
        ),
    )
    op.create_index(
        "ix_publisher_domains_publisher_active",
        "publisher_domains",
        ["publisher_id", "active"],
    )
    # Preserve source-registry coverage for publishers created before this migration.
    # Reusing the publisher UUID as the initial domain-row UUID is deterministic and safe
    # because the identifiers live in separate tables.
    op.execute(
        sa.text(
            """
            INSERT INTO publisher_domains (
                id, publisher_id, domain, homepage_url, edition_name, language, region,
                is_primary, active, discovered_via, metadata, created_at, updated_at
            )
            SELECT
                id, id, canonical_domain, homepage_url, NULL, NULL, NULL,
                TRUE, active, 'migration_backfill',
                jsonb_build_object('backfilled_from', 'publishers.canonical_domain'),
                created_at, updated_at
            FROM publishers
            """
        )
    )

    op.create_table(
        "robots_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "publisher_domain_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publisher_domains.id"),
            nullable=False,
        ),
        sa.Column("robots_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("body_sha256", sa.String(64)),
        sa.Column("body_text", sa.Text()),
        sa.Column("policy_state", sa.String(40), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_robots_snapshots_domain_fetched",
        "robots_snapshots",
        ["publisher_domain_id", "fetched_at"],
    )

    op.create_table(
        "source_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "discovered_from_publisher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publishers.id"),
        ),
        sa.Column("candidate_url", sa.Text(), nullable=False),
        sa.Column("candidate_domain", sa.String(253), nullable=False),
        sa.Column("evidence_type", sa.String(80), nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("score", sa.Float(), server_default="0", nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.UniqueConstraint("candidate_url", name="uq_source_candidates_url"),
    )
    op.create_index(
        "ix_source_candidates_state_score",
        "source_candidates",
        ["state", "score"],
    )
    op.create_index(
        "ix_source_candidates_domain",
        "source_candidates",
        ["candidate_domain"],
    )


def downgrade() -> None:
    op.drop_table("source_candidates")
    op.drop_table("robots_snapshots")
    op.drop_table("publisher_domains")
