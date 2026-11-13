"""Add channel opportunity discovery records.

Revision ID: c8f7d2a91b34
Revises: b71c0a9d2f41
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c8f7d2a91b34"
down_revision: Union[str, Sequence[str], None] = "b71c0a9d2f41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_idea_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("normalized_topic", sa.String(length=300), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("content_angle", sa.String(), nullable=True),
        sa.Column("source_evidence", sa.JSON(), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=False),
        sa.Column("score_total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("risk_flags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="discovered"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_idea_id"], ["content_ideas.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("channel_id", "normalized_topic", name="uq_channel_opportunity_topic"),
    )
    op.create_index(
        "ix_channel_opportunities_channel_score",
        "channel_opportunities", ["channel_id", "score_total"],
    )
    op.create_index(
        "ix_channel_opportunities_channel_status",
        "channel_opportunities", ["channel_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_opportunities_channel_status", table_name="channel_opportunities")
    op.drop_index("ix_channel_opportunities_channel_score", table_name="channel_opportunities")
    op.drop_table("channel_opportunities")
