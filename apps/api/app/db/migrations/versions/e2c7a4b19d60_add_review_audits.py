"""Add immutable human review audit records.

Revision ID: e2c7a4b19d60
Revises: d91e6a7c4b20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e2c7a4b19d60"
down_revision: Union[str, Sequence[str], None] = "d91e6a7c4b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reviewer", sa.String(length=160), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("previous_state", sa.String(length=64), nullable=False),
        sa.Column("new_state", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["content.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_review_audits_content_created",
        "review_audits",
        ["content_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_audits_content_created", table_name="review_audits")
    op.drop_table("review_audits")
