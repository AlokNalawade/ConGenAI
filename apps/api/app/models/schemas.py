from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

# --- Channel Schemas ---
class ChannelBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    niche: str = Field(min_length=2, max_length=160)
    description: Optional[str] = None
    target_audience: Optional[str] = None
    language: str = Field(default="en", min_length=2, max_length=16)
    platforms: List[str] = Field(default_factory=list)
    content_format: str = "short_form_video"
    target_duration_min: Optional[int] = Field(default=None, ge=1, le=3600)
    target_duration_max: Optional[int] = Field(default=None, ge=1, le=3600)
    brand_voice: Optional[str] = None
    visual_style: Optional[str] = None
    voice_profile: Optional[str] = None
    topic_boundaries: List[str] = Field(default_factory=list)
    excluded_topics: List[str] = Field(default_factory=list)
    research_sources: List[Dict[str, Any]] = Field(default_factory=list)
    monetization_strategy: Dict[str, Any] = Field(default_factory=dict)
    nightly_enabled: bool = True
    nightly_video_target: int = Field(default=2, ge=1, le=20)
    is_active: bool = True


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    niche: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = None
    target_audience: Optional[str] = None
    language: Optional[str] = Field(default=None, min_length=2, max_length=16)
    platforms: Optional[List[str]] = None
    content_format: Optional[str] = None
    target_duration_min: Optional[int] = Field(default=None, ge=1, le=3600)
    target_duration_max: Optional[int] = Field(default=None, ge=1, le=3600)
    brand_voice: Optional[str] = None
    visual_style: Optional[str] = None
    voice_profile: Optional[str] = None
    topic_boundaries: Optional[List[str]] = None
    excluded_topics: Optional[List[str]] = None
    research_sources: Optional[List[Dict[str, Any]]] = None
    monetization_strategy: Optional[Dict[str, Any]] = None
    nightly_enabled: Optional[bool] = None
    nightly_video_target: Optional[int] = Field(default=None, ge=1, le=20)
    is_active: Optional[bool] = None


class Channel(ChannelBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Content Idea Schemas ---
class ContentIdeaBase(BaseModel):
    channel_id: Optional[uuid.UUID] = None
    title: str
    description: Optional[str] = None
    topic: Optional[str] = None
    niche: Optional[str] = None
    target_audience: Optional[str] = None
    platform: Optional[str] = None
    content_type: Optional[str] = None
    priority: Optional[int] = 0
    status: Optional[str] = "new"
    source: Optional[str] = None

class ContentIdeaCreate(ContentIdeaBase):
    pass

class ContentIdeaUpdate(ContentIdeaBase):
    title: Optional[str] = None

class ContentIdea(ContentIdeaBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Content Schemas ---
class ContentBase(BaseModel):
    idea_id: Optional[uuid.UUID] = None
    channel_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    description: Optional[str] = None
    content_type: Optional[str] = None
    platform: Optional[str] = None
    target_duration: Optional[int] = None
    status: Optional[str] = "planning"
    quality_score: Optional[float] = None

class ContentCreate(ContentBase):
    pass

class ContentUpdate(ContentBase):
    pass

class Content(ContentBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Research Schemas ---
class ResearchBase(BaseModel):
    content_id: uuid.UUID
    summary: Optional[str] = None
    key_points: Optional[list] = None
    statistics: Optional[list] = None
    sources: Optional[list] = None
    competitor_analysis: Optional[list] = None
    hooks: Optional[list] = None
    warnings: Optional[list] = None

class ResearchCreate(ResearchBase):
    pass

class Research(ResearchBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

# --- Script Schemas ---
class ScriptBase(BaseModel):
    content_id: uuid.UUID
    version: Optional[int] = 1
    hook: Optional[str] = None
    body: Optional[str] = None
    cta: Optional[str] = None
    estimated_duration: Optional[int] = None
    word_count: Optional[int] = None
    status: Optional[str] = "draft"

class ScriptCreate(ScriptBase):
    pass

class Script(ScriptBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

# --- Scene Schemas ---
class SceneBase(BaseModel):
    content_id: uuid.UUID
    scene_number: Optional[int] = None
    duration: Optional[float] = None
    narration: Optional[str] = None
    visual_description: Optional[str] = None
    visual_prompt: Optional[str] = None
    onscreen_text: Optional[str] = None
    transition: Optional[str] = None
    sound_effect: Optional[str] = None
    status: Optional[str] = "pending"

class SceneCreate(SceneBase):
    pass

class Scene(SceneBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True

# --- Asset Schemas ---
class AssetBase(BaseModel):
    content_id: uuid.UUID
    scene_id: Optional[uuid.UUID] = None
    asset_type: Optional[str] = None
    filename: Optional[str] = None
    path: Optional[str] = None
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None

class AssetCreate(AssetBase):
    pass

class Asset(AssetBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
