from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Any, Type, TypeVar
import json
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ResearchResult(BaseModel):
    summary: str = Field(default="No summary provided.")
    key_points: List[str] = Field(default_factory=list)
    statistics: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    competitor_analysis: List[str] = Field(default_factory=list)
    hooks: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ScriptResult(BaseModel):
    hook: str = Field(..., description="First 3 seconds attention grabber")
    body: str = Field(..., description="Main content narrative")
    cta: str = Field(default="Follow for more!", description="Call to action")
    estimated_duration: int = Field(default=30, description="Estimated duration in seconds")
    word_count: int = Field(default=0, description="Total word count of script")

    def model_post_init(self, __context: Any) -> None:
        if self.word_count == 0 and (self.hook or self.body or self.cta):
            total_text = f"{self.hook} {self.body} {self.cta}"
            self.word_count = len(total_text.split())


class Scene(BaseModel):
    scene_number: int = Field(..., ge=1)
    duration: float = Field(default=5.0, gt=0.0)
    narration: str = Field(default="")
    visual_description: str = Field(default="")
    visual_prompt: str = Field(default="")
    onscreen_text: Optional[str] = None
    transition: Optional[str] = "none"
    sound_effect: Optional[str] = None


class ScenePlan(BaseModel):
    scenes: List[Scene] = Field(..., min_length=1)


class AssetSpec(BaseModel):
    asset_type: str = Field(..., description="image, audio, or video")
    prompt: Optional[str] = None
    duration: Optional[float] = None
    provider: Optional[str] = None


class QualityResult(BaseModel):
    overall_score: float = Field(default=0.0, ge=0.0, le=100.0)
    script_score: float = Field(default=0.0, ge=0.0, le=100.0)
    audio_score: float = Field(default=0.0, ge=0.0, le=100.0)
    video_score: float = Field(default=0.0, ge=0.0, le=100.0)
    passed: bool = Field(default=True)
    feedback: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


def validate_ai_response(raw_input: Any, model_cls: Type[T]) -> T:
    """
    Safely validates and parses LLM raw responses into strongly-typed Pydantic contracts.
    Accepts dicts, strings (JSON), or existing model instances.
    """
    if isinstance(raw_input, model_cls):
        return raw_input

    data = raw_input
    if isinstance(raw_input, str):
        try:
            data = json.loads(raw_input)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output string: {e}")
            raise ValueError(f"Invalid JSON string returned by LLM: {raw_input[:100]}...") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected dict or JSON string for {model_cls.__name__}, got {type(data)}")

    try:
        return model_cls.model_validate(data)
    except ValidationError as ve:
        logger.warning(f"Validation error parsing {model_cls.__name__}: {ve}")
        # If strict validation fails, attempt best-effort field coercion or raise
        raise ValueError(f"LLM output failed schema contract for {model_cls.__name__}: {ve}") from ve
