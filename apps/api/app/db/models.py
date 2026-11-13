from sqlalchemy import Column, String, DateTime, func, JSON, Float, Integer, ForeignKey, UniqueConstraint, Index, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Channel(Base):
    """Independent editorial identity and nightly production configuration."""
    __tablename__ = "channels"
    __table_args__ = (
        CheckConstraint(
            "nightly_video_target >= 1 AND nightly_video_target <= 20",
            name="ck_channels_nightly_video_target_range",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    slug = Column(String(80), nullable=False, unique=True, index=True)
    niche = Column(String(160), nullable=False)
    description = Column(String, nullable=True)
    target_audience = Column(String, nullable=True)
    language = Column(String(16), nullable=False, default="en", server_default="en")
    platforms = Column(JSON, nullable=False, default=list)
    content_format = Column(String(80), nullable=False, default="short_form_video", server_default="short_form_video")
    target_duration_min = Column(Integer, nullable=True)
    target_duration_max = Column(Integer, nullable=True)
    brand_voice = Column(String, nullable=True)
    visual_style = Column(String, nullable=True)
    voice_profile = Column(String, nullable=True)
    topic_boundaries = Column(JSON, nullable=False, default=list)
    excluded_topics = Column(JSON, nullable=False, default=list)
    research_sources = Column(JSON, nullable=False, default=list)
    monetization_strategy = Column(JSON, nullable=False, default=dict)
    nightly_enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    nightly_video_target = Column(Integer, nullable=False, default=2, server_default="2")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ideas = relationship("ContentIdea", back_populates="channel")
    contents = relationship("Content", back_populates="channel")
    topic_history = relationship("ChannelTopicHistory", cascade="all, delete-orphan")
    batches = relationship("ContentBatch", back_populates="channel")
    opportunities = relationship("ChannelOpportunity", back_populates="channel", cascade="all, delete-orphan")


class ContentIdea(Base):
    __tablename__ = "content_ideas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="RESTRICT"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    topic = Column(String)
    niche = Column(String)
    target_audience = Column(String)
    platform = Column(String)
    content_type = Column(String)
    priority = Column(Integer)
    status = Column(String)
    source = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    channel = relationship("Channel", back_populates="ideas")
    contents = relationship("Content", back_populates="idea")

class ChannelTopicHistory(Base):
    """Topics reserved or produced for a channel, preventing duplicate ideas."""
    __tablename__ = "channel_topic_history"
    __table_args__ = (
        UniqueConstraint("channel_id", "normalized_topic", name="uq_channel_topic_history_topic"),
        Index("ix_channel_topic_history_channel_seen", "channel_id", "first_seen_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    normalized_topic = Column(String(300), nullable=False)
    topic = Column(String, nullable=False)
    content_idea_id = Column(UUID(as_uuid=True), ForeignKey("content_ideas.id", ondelete="SET NULL"), nullable=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="SET NULL"), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChannelOpportunity(Base):
    """Evidence-backed editorial candidate, isolated to one channel."""
    __tablename__ = "channel_opportunities"
    __table_args__ = (
        UniqueConstraint("channel_id", "normalized_topic", name="uq_channel_opportunity_topic"),
        Index("ix_channel_opportunities_channel_score", "channel_id", "score_total"),
        Index("ix_channel_opportunities_channel_status", "channel_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    content_idea_id = Column(UUID(as_uuid=True), ForeignKey("content_ideas.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(500), nullable=False)
    normalized_topic = Column(String(300), nullable=False)
    description = Column(String, nullable=True)
    content_angle = Column(String, nullable=True)
    source_evidence = Column(JSON, nullable=False, default=list)
    score_breakdown = Column(JSON, nullable=False, default=dict)
    score_total = Column(Float, nullable=False, default=0.0)
    confidence = Column(Integer, nullable=False, default=0)
    rationale = Column(String, nullable=True)
    risk_flags = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="discovered")
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    selected_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    channel = relationship("Channel", back_populates="opportunities")


class NightlyProductionRun(Base):
    """One user-triggered nightly factory execution across enabled channels."""
    __tablename__ = "nightly_production_runs"
    __table_args__ = (
        Index("ix_nightly_production_runs_created", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(32), nullable=False, default="running")
    idempotency_key = Column(String(160), nullable=True, unique=True)
    requested_total = Column(Integer, nullable=False, default=0)
    queued_total = Column(Integer, nullable=False, default=0)
    failed_total = Column(Integer, nullable=False, default=0)
    config_json = Column(JSON, nullable=False, default=dict)
    error = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    channel_runs = relationship(
        "NightlyChannelRun", back_populates="nightly_run",
        cascade="all, delete-orphan", order_by="NightlyChannelRun.created_at",
    )


class NightlyChannelRun(Base):
    """Per-channel discovery and production allocation within a nightly run."""
    __tablename__ = "nightly_channel_runs"
    __table_args__ = (
        UniqueConstraint("nightly_run_id", "channel_id", name="uq_nightly_run_channel"),
        Index("ix_nightly_channel_runs_channel_status", "channel_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nightly_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("nightly_production_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id = Column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False,
    )
    target_count = Column(Integer, nullable=False)
    selected_count = Column(Integer, nullable=False, default=0)
    queued_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending")
    discovery_json = Column(JSON, nullable=True)
    content_ids = Column(JSON, nullable=False, default=list)
    job_ids = Column(JSON, nullable=False, default=list)
    error = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    nightly_run = relationship("NightlyProductionRun", back_populates="channel_runs")
    channel = relationship("Channel")


class ContentBatch(Base):
    __tablename__ = "content_batches"
    id = Column(String, primary_key=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="RESTRICT"), nullable=True, index=True)
    topic = Column(String, nullable=False)
    requested_count = Column(Integer, default=1)
    status = Column(String, default="queued")
    successful_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    contents = relationship("Content", back_populates="batch")
    channel = relationship("Channel", back_populates="batches")

class Content(Base):
    __tablename__ = "content"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idea_id = Column(UUID(as_uuid=True), ForeignKey("content_ideas.id"), nullable=True)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="RESTRICT"), nullable=True, index=True)
    batch_id = Column(String, ForeignKey("content_batches.id"), nullable=True)
    title = Column(String)
    description = Column(String)
    content_type = Column(String)
    platform = Column(String)
    target_duration = Column(Integer)
    status = Column(String)
    quality_score = Column(Float)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    channel = relationship("Channel", back_populates="contents")
    idea = relationship("ContentIdea", back_populates="contents")
    batch = relationship("ContentBatch", back_populates="contents")
    research = relationship("Research", back_populates="content", uselist=False)
    strategy = relationship("Strategy", back_populates="content", uselist=False)
    scripts = relationship("Script", back_populates="content")
    scenes = relationship("Scene", back_populates="content")
    assets = relationship("Asset", back_populates="content")
    pipeline_runs = relationship("PipelineRun", back_populates="content", foreign_keys="[PipelineRun.content_id]")
    jobs = relationship("PipelineJobDB", back_populates="content")

class PipelineJobDB(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        Index('ix_job_content_idempotency', 'content_id', 'idempotency_key', unique=True, postgresql_where="idempotency_key IS NOT NULL"),
        Index('ix_one_active_job_per_content', 'content_id', unique=True, postgresql_where="status IN ('queued', 'dispatching', 'running', 'resuming')"),
    )
    id = Column(String, primary_key=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    idempotency_key = Column(String, nullable=True)
    status = Column(String, default="queued")
    current_stage = Column(String, default="NEW")
    progress_percent = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    error = Column(String, nullable=True)
    model_overrides = Column(JSON, nullable=True)
    resume = Column(Integer, default=1)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="jobs")

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    parent_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    is_current = Column(Integer, default=1)
    run_type = Column(String, default="initial")
    reason = Column(String, nullable=True)
    status = Column(String, default="running")
    current_stage = Column(String, default="NEW")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String, nullable=True)
    model_overrides = Column(JSON, nullable=True)
    input_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="pipeline_runs", foreign_keys=[content_id])

class Research(Base):
    __tablename__ = "research"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    summary = Column(String)
    key_points = Column(JSON)
    statistics = Column(JSON)
    sources = Column(JSON)
    competitor_analysis = Column(JSON)
    hooks = Column(JSON)
    warnings = Column(JSON)
    status = Column(String, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="research")

class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    content_angle = Column(String)
    target_audience_analysis = Column(String)
    hook_strategy = Column(String)
    format_guidelines = Column(JSON)
    status = Column(String, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="strategy")

class Script(Base):
    __tablename__ = "scripts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    version = Column(Integer, default=1)
    hook = Column(String)
    body = Column(String)
    cta = Column(String)
    estimated_duration = Column(Integer)
    word_count = Column(Integer)
    status = Column(String, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="scripts")

class Prompt(Base):
    __tablename__ = "prompts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    agent = Column(String)
    version = Column(Integer, default=1)
    template = Column(String)
    parameters = Column(JSON)
    active = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AIModel(Base):
    __tablename__ = "models"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    provider = Column(String)
    model_name = Column(String)
    capability = Column(String)
    context_length = Column(Integer)
    quantization = Column(String)
    vram_required = Column(Float)
    active = Column(Integer, default=1)

class Scene(Base):
    __tablename__ = "scenes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    scene_number = Column(Integer)
    duration = Column(Float)
    narration = Column(String)
    visual_description = Column(String)
    visual_prompt = Column(String)
    onscreen_text = Column(String)
    transition = Column(String)
    sound_effect = Column(String)
    status = Column(String, default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="scenes")
    assets = relationship("Asset", back_populates="scene")

class Asset(Base):
    __tablename__ = "assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id"), nullable=True)
    parent_asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    version = Column(Integer, default=1)
    asset_type = Column(String)
    filename = Column(String)
    path = Column(String)
    mime_type = Column(String)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)
    provider = Column(String)
    model = Column(String)
    prompt = Column(String, nullable=True)
    negative_prompt = Column(String, nullable=True)
    seed = Column(Integer, nullable=True)
    workflow = Column(String, nullable=True)
    sha256 = Column(String, nullable=True)
    status = Column(String, default="completed")
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="assets")
    scene = relationship("Scene", back_populates="assets")

class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    stage = Column(String)
    agent = Column(String)
    provider = Column(String)
    model = Column(String)
    prompt_version = Column(Integer, default=1)
    duration_seconds = Column(Float)
    status = Column(String)
    error = Column(String, nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Source(Base):
    __tablename__ = "sources"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_id = Column(UUID(as_uuid=True), ForeignKey("research.id"))
    url = Column(String)
    title = Column(String)
    publisher = Column(String)
    published_at = Column(String, nullable=True)
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now())
    credibility = Column(Float, default=1.0)
    evidence_items = relationship("Evidence", back_populates="source")

class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"))
    claim = Column(String)
    supporting_text = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    source = relationship("Source", back_populates="evidence_items")

class ContentDNA(Base):
    __tablename__ = "content_dna"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    topic = Column(String)
    niche = Column(String)
    hook_type = Column(String)
    video_length = Column(Float)
    script_structure = Column(String)
    cta = Column(String)
    visual_style = Column(String)
    voice = Column(String)
    views = Column(Integer, default=0)
    retention = Column(Float, default=0.0)
    likes = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Publication(Base):
    __tablename__ = "publications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    platform = Column(String)
    post_url = Column(String, nullable=True)
    status = Column(String, default="scheduled")
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id = Column(UUID(as_uuid=True), ForeignKey("publications.id"))
    views = Column(Integer, default=0)
    watch_time = Column(Float, default=0.0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    retention_rate = Column(Float, default=0.0)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())

class Experiment(Base):
    __tablename__ = "experiments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    name = Column(String)
    variant_a = Column(JSON)
    variant_b = Column(JSON)
    winner = Column(String, nullable=True)
    status = Column(String, default="running")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
