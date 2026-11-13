"""Add persistent nightly production orchestration records.

Revision ID: d91e6a7c4b20
Revises: c8f7d2a91b34
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d91e6a7c4b20"
down_revision: Union[str, Sequence[str], None] = "c8f7d2a91b34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nightly_production_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("requested_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_nightly_production_runs_idempotency_key"),
    )
    op.create_index(
        "ix_nightly_production_runs_created",
        "nightly_production_runs", ["created_at"],
    )
    op.create_index(
        "ix_one_active_nightly_run",
        "nightly_production_runs",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'dispatching')"),
    )
    op.create_table(
        "nightly_channel_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("nightly_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("discovery_json", sa.JSON(), nullable=True),
        sa.Column("content_ids", sa.JSON(), nullable=False),
        sa.Column("job_ids", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["nightly_run_id"], ["nightly_production_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("nightly_run_id", "channel_id", name="uq_nightly_run_channel"),
    )
    op.create_index(
        "ix_nightly_channel_runs_channel_status",
        "nightly_channel_runs", ["channel_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_nightly_channel_runs_channel_status", table_name="nightly_channel_runs")
    op.drop_table("nightly_channel_runs")
    op.drop_index("ix_one_active_nightly_run", table_name="nightly_production_runs")
    op.drop_index("ix_nightly_production_runs_created", table_name="nightly_production_runs")
    op.drop_table("nightly_production_runs")
