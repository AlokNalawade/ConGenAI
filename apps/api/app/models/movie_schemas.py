from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MovieProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    logline: str | None = Field(default=None, max_length=2000)
    synopsis: str | None = None
    genre_ids: list[str] = Field(default_factory=lambda: ["science_fiction"], max_length=8)
    language: str = Field(default="en", min_length=2, max_length=16)
    runtime_seconds: int = Field(default=900, ge=30, le=21600)
    project_format: str = Field(default="standalone_short", max_length=40)
    rating_target: str | None = Field(default="parental_guidance", max_length=40)
    visual_style: str = Field(default="photorealistic_cinematic", max_length=120)
    resolution: str = Field(default="1080p", pattern=r"^(720p|1080p|1440p|4k)$")
    execution_mode: str = Field(default="hybrid", pattern=r"^(local|cloud|hybrid)$")
    approval_mode: str = Field(default="manual", pattern=r"^manual$")
    auto_publish: bool = False
    budget_currency: str = Field(default="CAD", min_length=3, max_length=3)
    max_total_cost: float | None = Field(default=None, gt=0)
    settings_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("genre_ids")
    @classmethod
    def unique_genres(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
        if len(cleaned) > 8:
            raise ValueError("At most 8 genre profiles may be combined")
        return cleaned

    @model_validator(mode="after")
    def enforce_manual_review(self):
        if self.auto_publish:
            raise ValueError("Movie Studio does not support automatic publishing")
        if self.approval_mode != "manual":
            raise ValueError("Movie Studio requires manual approval")
        return self


class MovieProjectUpdate(BaseModel):
    @field_validator("genre_ids")
    @classmethod
    def unique_genres(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(item.strip().lower() for item in value if item.strip()))
    title: str | None = Field(default=None, min_length=1, max_length=240)
    logline: str | None = Field(default=None, max_length=2000)
    synopsis: str | None = None
    genre_ids: list[str] | None = Field(default=None, max_length=8)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    runtime_seconds: int | None = Field(default=None, ge=30, le=21600)
    project_format: str | None = Field(default=None, max_length=40)
    rating_target: str | None = Field(default=None, max_length=40)
    visual_style: str | None = Field(default=None, max_length=120)
    resolution: str | None = Field(default=None, pattern=r"^(720p|1080p|1440p|4k)$")
    execution_mode: str | None = Field(default=None, pattern=r"^(local|cloud|hybrid)$")
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    max_total_cost: float | None = Field(default=None, gt=0)
    settings_json: dict[str, Any] | None = None


class MovieProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    logline: str | None
    synopsis: str | None
    genre_ids: list[str]
    language: str
    runtime_seconds: int
    project_format: str
    rating_target: str | None
    visual_style: str
    resolution: str
    execution_mode: str
    approval_mode: str
    auto_publish: bool
    status: str
    budget_currency: str
    max_total_cost: float | None
    settings_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None = None


class MovieSceneCreate(BaseModel):
    scene_number: int = Field(ge=1)
    heading: str | None = Field(default=None, max_length=500)
    summary: str | None = None
    screenplay_text: str | None = None
    location_bible: dict[str, Any] = Field(default_factory=dict)


class MovieShotCreate(BaseModel):
    shot_number: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=240)
    beat: str | None = None
    visual_prompt: str | None = None
    target_duration_seconds: float = Field(default=5.0, gt=0, le=30)
    camera: dict[str, Any] = Field(default_factory=dict)
    character_refs: list[str] = Field(default_factory=list)
    prop_refs: list[str] = Field(default_factory=list)
    continuity: dict[str, Any] = Field(default_factory=dict)
