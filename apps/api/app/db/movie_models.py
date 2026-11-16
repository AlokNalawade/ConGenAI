"""Persistence models for the independent Movie Studio domain.

These tables intentionally do not reuse Content or PipelineJobDB: film projects,
scenes, shots and takes have a different lifecycle and retry granularity.
"""
import uuid

from sqlalchemy import (
    Column, String, DateTime, Float, Integer, ForeignKey, JSON, Boolean,
    UniqueConstraint, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class MovieProject(Base):
    __tablename__ = "movie_projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(240), nullable=False)
    logline = Column(String(2000), nullable=True)
    synopsis = Column(String, nullable=True)
    genre_ids = Column(JSON, nullable=False, default=list)
    language = Column(String(16), nullable=False, default="en")
    runtime_seconds = Column(Integer, nullable=False, default=900)
    project_format = Column(String(40), nullable=False, default="standalone_short")
    rating_target = Column(String(40), nullable=True)
    visual_style = Column(String(120), nullable=False, default="photorealistic_cinematic")
    resolution = Column(String(16), nullable=False, default="1080p")
    execution_mode = Column(String(16), nullable=False, default="hybrid")
    approval_mode = Column(String(16), nullable=False, default="manual")
    auto_publish = Column(Boolean, nullable=False, default=False)
    status = Column(String(40), nullable=False, default="draft_brief", index=True)
    budget_currency = Column(String(3), nullable=False, default="CAD")
    max_total_cost = Column(Float, nullable=True)
    settings_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MovieScene(Base):
    __tablename__ = "movie_scenes"
    __table_args__ = (UniqueConstraint("project_id", "scene_number", name="uq_movie_scene_order"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("movie_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_number = Column(Integer, nullable=False)
    heading = Column(String(500), nullable=True)
    summary = Column(String, nullable=True)
    screenplay_text = Column(String, nullable=True)
    location_bible = Column(JSON, nullable=False, default=dict)
    status = Column(String(40), nullable=False, default="planned")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MovieShot(Base):
    __tablename__ = "movie_shots"
    __table_args__ = (UniqueConstraint("scene_id", "shot_number", name="uq_movie_shot_order"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("movie_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(UUID(as_uuid=True), ForeignKey("movie_scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_number = Column(Integer, nullable=False)
    title = Column(String(240), nullable=True)
    beat = Column(String, nullable=True)
    visual_prompt = Column(String, nullable=True)
    target_duration_seconds = Column(Float, nullable=False, default=5.0)
    camera = Column(JSON, nullable=False, default=dict)
    character_refs = Column(JSON, nullable=False, default=list)
    prop_refs = Column(JSON, nullable=False, default=list)
    continuity = Column(JSON, nullable=False, default=dict)
    status = Column(String(40), nullable=False, default="planned", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MovieTake(Base):
    __tablename__ = "movie_takes"
    __table_args__ = (
        UniqueConstraint("shot_id", "attempt_number", name="uq_movie_take_attempt"),
        Index("ix_movie_takes_shot_status", "shot_id", "status"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shot_id = Column(UUID(as_uuid=True), ForeignKey("movie_shots.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    provider = Column(String(80), nullable=True)
    model = Column(String(160), nullable=True)
    prompt_version = Column(Integer, nullable=False, default=1)
    output_path = Column(String, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    cost = Column(Float, nullable=True)
    status = Column(String(40), nullable=False, default="queued")
    qa_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResourceLease(Base):
    """Durable reservation record; admission policy/worker integration is a later step."""
    __tablename__ = "resource_leases"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(String(160), nullable=False, unique=True)
    division = Column(String(40), nullable=False, index=True)
    owner_id = Column(String(160), nullable=False)
    resource_type = Column(String(40), nullable=False)
    units = Column(Integer, nullable=False, default=1)
    state = Column(String(24), nullable=False, default="reserved", index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    released_at = Column(DateTime(timezone=True), nullable=True)
