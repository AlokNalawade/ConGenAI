from sqlalchemy import Column, String, DateTime, func, JSON, Float, Integer, ForeignKey, UniqueConstraint, Index
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

class ContentIdea(Base):
    __tablename__ = "content_ideas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    contents = relationship("Content", back_populates="idea")

class ContentBatch(Base):
    __tablename__ = "content_batches"
    id = Column(String, primary_key=True)
    topic = Column(String, nullable=False)
    requested_count = Column(Integer, default=1)
    status = Column(String, default="queued")
    successful_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    contents = relationship("Content", back_populates="batch")

class Content(Base):
    __tablename__ = "content"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idea_id = Column(UUID(as_uuid=True), ForeignKey("content_ideas.id"), nullable=True)
    batch_id = Column(String, ForeignKey("content_batches.id"), nullable=True)
    title = Column(String)
    description = Column(String)
    content_type = Column(String)
    platform = Column(String)
    target_duration = Column(Integer)
    status = Column(String)
    quality_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    idea = relationship("ContentIdea", back_populates="contents")
    batch = relationship("ContentBatch", back_populates="contents")
    research = relationship("Research", back_populates="content", uselist=False)
    strategy = relationship("Strategy", back_populates="content", uselist=False)
    scripts = relationship("Script", back_populates="content")
    scenes = relationship("Scene", back_populates="content")
    assets = relationship("Asset", back_populates="content")
    pipeline_runs = relationship("PipelineRun", back_populates="content")
    jobs = relationship("PipelineJobDB", back_populates="content")

class PipelineJobDB(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        Index('ix_job_content_idempotency', 'content_id', 'idempotency_key', unique=True, postgresql_where="idempotency_key IS NOT NULL"),
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
    pipeline_run_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="jobs")

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    status = Column(String, default="running")
    current_stage = Column(String, default="NEW")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String, nullable=True)
    model_overrides = Column(JSON, nullable=True)
    input_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="pipeline_runs")

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
    scene = relationship("Scene", back_populates="scene") if False else relationship("Scene", back_populates="assets")

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
