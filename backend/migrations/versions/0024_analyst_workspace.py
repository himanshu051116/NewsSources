"""analyst investigations, watchlists, notes and saved searches

Revision ID: 0024_analyst_workspace
Revises: 0023_blind_adjudication_diagnostics
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0024_analyst_workspace"
down_revision: str | None = "0023_blind_adjudication_diagnostics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_investigations_owner_status_updated", "investigations", ["owner_user_id", "status", "updated_at"])

    op.create_table(
        "investigation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("item_type", sa.String(length=40), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_snapshot", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("investigation_id", "item_type", "item_id", name="uq_investigation_item_target"),
    )
    op.create_index("ix_investigation_items_investigation_created", "investigation_items", ["investigation_id", "created_at"])
    op.create_index("ix_investigation_items_target", "investigation_items", ["item_type", "item_id"])

    op.create_table(
        "analyst_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id"), nullable=True),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False, server_default="investigation"),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analyst_notes_investigation_created", "analyst_notes", ["investigation_id", "created_at"])
    op.create_index("ix_analyst_notes_target", "analyst_notes", ["target_type", "target_id"])

    op.create_table(
        "saved_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("investigations.id"), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_saved_search_owner_name"),
    )
    op.create_index("ix_saved_searches_owner_updated", "saved_searches", ["owner_user_id", "updated_at"])

    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_watchlist_owner_name"),
    )
    op.create_index("ix_watchlists_owner_updated", "watchlists", ["owner_user_id", "updated_at"])

    op.create_table(
        "watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("item_type", sa.String(length=40), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_snapshot", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("watchlist_id", "item_type", "item_id", name="uq_watchlist_item_target"),
    )
    op.create_index("ix_watchlist_items_watchlist_created", "watchlist_items", ["watchlist_id", "created_at"])
    op.create_index("ix_watchlist_items_target", "watchlist_items", ["item_type", "item_id"])

    op.create_table(
        "workspace_alert_acknowledgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_users.id"), nullable=False),
        sa.Column("alert_key", sa.String(length=300), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "alert_key", name="uq_workspace_alert_ack_user_key"),
    )
    op.create_index("ix_workspace_alert_ack_user_created", "workspace_alert_acknowledgements", ["user_id", "acknowledged_at"])


def downgrade() -> None:
    op.drop_index("ix_workspace_alert_ack_user_created", table_name="workspace_alert_acknowledgements")
    op.drop_table("workspace_alert_acknowledgements")
    op.drop_index("ix_watchlist_items_target", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_watchlist_created", table_name="watchlist_items")
    op.drop_table("watchlist_items")
    op.drop_index("ix_watchlists_owner_updated", table_name="watchlists")
    op.drop_table("watchlists")
    op.drop_index("ix_saved_searches_owner_updated", table_name="saved_searches")
    op.drop_table("saved_searches")
    op.drop_index("ix_analyst_notes_target", table_name="analyst_notes")
    op.drop_index("ix_analyst_notes_investigation_created", table_name="analyst_notes")
    op.drop_table("analyst_notes")
    op.drop_index("ix_investigation_items_target", table_name="investigation_items")
    op.drop_index("ix_investigation_items_investigation_created", table_name="investigation_items")
    op.drop_table("investigation_items")
    op.drop_index("ix_investigations_owner_status_updated", table_name="investigations")
    op.drop_table("investigations")
