"""Add channel profiles and channel ownership to ideas and content.

Revision ID: b71c0a9d2f41
Revises: 5a33285fa474
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b71c0a9d2f41"
down_revision: Union[str, Sequence[str], None] = "5a33285fa474"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("niche", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("target_audience", sa.String(), nullable=True),
        sa.Column("language", sa.String(length=16), server_default="en", nullable=False),
        sa.Column("platforms", sa.JSON(), nullable=False),
        sa.Column("content_format", sa.String(length=80), server_default="short_form_video", nullable=False),
        sa.Column("target_duration_min", sa.Integer(), nullable=True),
        sa.Column("target_duration_max", sa.Integer(), nullable=True),
        sa.Column("brand_voice", sa.String(), nullable=True),
        sa.Column("visual_style", sa.String(), nullable=True),
        sa.Column("voice_profile", sa.String(), nullable=True),
        sa.Column("topic_boundaries", sa.JSON(), nullable=False),
        sa.Column("excluded_topics", sa.JSON(), nullable=False),
        sa.Column("research_sources", sa.JSON(), nullable=False),
        sa.Column("monetization_strategy", sa.JSON(), nullable=False),
        sa.Column("nightly_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("nightly_video_target", sa.Integer(), server_default="2", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("slug", name="uq_channels_slug"),
        sa.CheckConstraint(
            "nightly_video_target >= 1 AND nightly_video_target <= 20",
            name="ck_channels_nightly_video_target_range",
        ),
    )
    op.create_index("ix_channels_slug", "channels", ["slug"], unique=True)
    op.add_column("content_ideas", sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_content_ideas_channel_id", "content_ideas", ["channel_id"])
    op.create_foreign_key(
        "fk_content_ideas_channel_id_channels",
        "content_ideas", "channels", ["channel_id"], ["id"], ondelete="RESTRICT",
    )
    op.add_column("content", sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_content_channel_id", "content", ["channel_id"])
    op.create_foreign_key(
        "fk_content_channel_id_channels",
        "content", "channels", ["channel_id"], ["id"], ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_content_channel_id_channels", "content", type_="foreignkey")
    op.drop_index("ix_content_channel_id", table_name="content")
    op.drop_column("content", "channel_id")
    op.drop_constraint("fk_content_ideas_channel_id_channels", "content_ideas", type_="foreignkey")
    op.drop_index("ix_content_ideas_channel_id", table_name="content_ideas")
    op.drop_column("content_ideas", "channel_id")
    op.drop_index("ix_channels_slug", table_name="channels")
    op.drop_table("channels")
