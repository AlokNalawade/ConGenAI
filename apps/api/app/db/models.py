from sqlalchemy import Column, String, DateTime, func, JSON, Float, Integer, ForeignKey
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

class Content(Base):
    __tablename__ = "content"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idea_id = Column(UUID(as_uuid=True), ForeignKey("content_ideas.id"))
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
    research = relationship("Research", back_populates="content", uselist=False)
    scripts = relationship("Script", back_populates="content")
    scenes = relationship("Scene", back_populates="content")
    assets = relationship("Asset", back_populates="content")

class Research(Base):
    __tablename__ = "research"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    summary = Column(String)
    key_points = Column(JSON)
    statistics = Column(JSON)
    sources = Column(JSON)
    competitor_analysis = Column(JSON)
    hooks = Column(JSON)
    warnings = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="research")

class Script(Base):
    __tablename__ = "scripts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    version = Column(Integer, default=1)
    hook = Column(String)
    body = Column(String)
    cta = Column(String)
    estimated_duration = Column(Integer)
    word_count = Column(Integer)
    status = Column(String)
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
    scene_number = Column(Integer)
    duration = Column(Float)
    narration = Column(String)
    visual_description = Column(String)
    visual_prompt = Column(String)
    onscreen_text = Column(String)
    transition = Column(String)
    sound_effect = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="scenes")
    assets = relationship("Asset", back_populates="scene")

class Asset(Base):
    __tablename__ = "assets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id"))
    scene_id = Column(UUID(as_uuid=True), ForeignKey("scenes.id"), nullable=True)
    asset_type = Column(String)
    filename = Column(String)
    path = Column(String)
    mime_type = Column(String)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)
    provider = Column(String)
    model = Column(String)
    metadata_json = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    content = relationship("Content", back_populates="assets")
    scene = relationship("Scene", back_populates="assets")
