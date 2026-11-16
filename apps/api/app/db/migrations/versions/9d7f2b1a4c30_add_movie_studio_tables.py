"""Add Movie Studio project and shot-planning tables.

Revision ID: 9d7f2b1a4c30
Revises: 5a33285fa474
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9d7f2b1a4c30"
down_revision: Union[str, Sequence[str], None] = "5a33285fa474"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "movie_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("logline", sa.String(2000)),
        sa.Column("synopsis", sa.String()),
        sa.Column("genre_ids", sa.JSON(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("runtime_seconds", sa.Integer(), nullable=False),
        sa.Column("project_format", sa.String(40), nullable=False),
        sa.Column("rating_target", sa.String(40)),
        sa.Column("visual_style", sa.String(120), nullable=False),
        sa.Column("resolution", sa.String(16), nullable=False),
        sa.Column("execution_mode", sa.String(16), nullable=False),
        sa.Column("approval_mode", sa.String(16), nullable=False),
        sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft_brief"),
        sa.Column("budget_currency", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("max_total_cost", sa.Float()),
        sa.Column("settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_movie_projects_status", "movie_projects", ["status"])

    op.create_table(
        "movie_scenes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("movie_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(500)),
        sa.Column("summary", sa.String()),
        sa.Column("screenplay_text", sa.String()),
        sa.Column("location_bible", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(40), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "scene_number", name="uq_movie_scene_order"),
    )
    op.create_index("ix_movie_scenes_project_id", "movie_scenes", ["project_id"])

    op.create_table(
        "movie_shots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("movie_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("movie_scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240)),
        sa.Column("beat", sa.String()),
        sa.Column("visual_prompt", sa.String()),
        sa.Column("target_duration_seconds", sa.Float(), nullable=False, server_default="5"),
        sa.Column("camera", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("character_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("prop_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("continuity", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(40), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scene_id", "shot_number", name="uq_movie_shot_order"),
    )
    op.create_index("ix_movie_shots_project_id", "movie_shots", ["project_id"])
    op.create_index("ix_movie_shots_scene_id", "movie_shots", ["scene_id"])
    op.create_index("ix_movie_shots_status", "movie_shots", ["status"])

    op.create_table(
        "movie_takes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("movie_shots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(80)),
        sa.Column("model", sa.String(160)),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("output_path", sa.String()),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("cost", sa.Float()),
        sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
        sa.Column("qa_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shot_id", "attempt_number", name="uq_movie_take_attempt"),
    )
    op.create_index("ix_movie_takes_shot_id", "movie_takes", ["shot_id"])
    op.create_index("ix_movie_takes_shot_status", "movie_takes", ["shot_id", "status"])

    op.create_table(
        "resource_leases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.String(160), nullable=False, unique=True),
        sa.Column("division", sa.String(40), nullable=False),
        sa.Column("owner_id", sa.String(160), nullable=False),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(24), nullable=False, server_default="reserved"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_resource_leases_division", "resource_leases", ["division"])
    op.create_index("ix_resource_leases_state", "resource_leases", ["state"])


def downgrade() -> None:
    op.drop_index("ix_resource_leases_state", table_name="resource_leases")
    op.drop_index("ix_resource_leases_division", table_name="resource_leases")
    op.drop_table("resource_leases")
    op.drop_index("ix_movie_takes_shot_status", table_name="movie_takes")
    op.drop_index("ix_movie_takes_shot_id", table_name="movie_takes")
    op.drop_table("movie_takes")
    op.drop_index("ix_movie_shots_status", table_name="movie_shots")
    op.drop_index("ix_movie_shots_scene_id", table_name="movie_shots")
    op.drop_index("ix_movie_shots_project_id", table_name="movie_shots")
    op.drop_table("movie_shots")
    op.drop_index("ix_movie_scenes_project_id", table_name="movie_scenes")
    op.drop_table("movie_scenes")
    op.drop_index("ix_movie_projects_status", table_name="movie_projects")
    op.drop_table("movie_projects")
