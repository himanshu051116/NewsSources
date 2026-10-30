"""historical context quality and reconciliation metadata

Revision ID: 0019_historical_context_quality
Revises: 0018_historical_enrichment
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_historical_context_quality"
down_revision: str | None = "0018_historical_enrichment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "article_historical_enrichment_jobs",
        sa.Column("refresh_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "article_historical_enrichment_jobs",
        sa.Column("last_refresh_reason", sa.String(120), nullable=True),
    )
    op.add_column(
        "article_historical_enrichment_jobs",
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("article_historical_enrichment_jobs", "last_reconciled_at")
    op.drop_column("article_historical_enrichment_jobs", "last_refresh_reason")
    op.drop_column("article_historical_enrichment_jobs", "refresh_count")
