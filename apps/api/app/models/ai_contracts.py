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


class StrategyResult(BaseModel):
    content_angle: str = Field(default="Educational Overview", description="Core perspective or angle for the video")
    target_audience_analysis: str = Field(default="General Tech Enthusiasts", description="Insights on audience preferences")
    hook_strategy: str = Field(default="Curiosity Gap", description="Framework used for the video hook")
    format_guidelines: List[str] = Field(default_factory=list, description="Visual and narrative format constraints")


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
        # Calculate estimated duration based on 150 WPM (2.5 words/sec) if not supplied or zero
        if self.estimated_duration == 0 or self.estimated_duration == 30:
            if self.word_count > 0:
                self.estimated_duration = max(5, int(self.word_count / 2.5))


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

    def validate_consistency(self, target_duration: Optional[float] = None) -> bool:
        """
        Enforces scene continuity and duration bounds.
        """
        sorted_scenes = sorted(self.scenes, key=lambda s: s.scene_number)
        numbers = [s.scene_number for s in sorted_scenes]
        expected_numbers = list(range(1, len(self.scenes) + 1))
        
        if numbers != expected_numbers:
            raise ValueError(f"Scene numbers are not contiguous: expected {expected_numbers}, got {numbers}")
            
        total_duration = sum(s.duration for s in self.scenes)
        if target_duration and target_duration > 0:
            allowed_diff = max(5.0, 0.20 * target_duration)
            if abs(total_duration - target_duration) > allowed_diff:
                logger.warning(
                    f"Scene plan duration ({total_duration:.1f}s) deviates from target script duration ({target_duration:.1f}s) by more than allowed threshold ({allowed_diff:.1f}s)."
                )
        return True


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
    passed: bool = Field(default=False)  # Fail closed by default
    feedback: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


def validate_ai_response(raw_input: Any, model_cls: Type[T]) -> T:
    """
    Safely validates and parses LLM raw responses into strongly-typed Pydantic contracts.
    Accepts dicts, strings (JSON), or existing model instances.
    Coerces dicts/lists into strings when LLMs output structured objects for string fields.
    """
    if isinstance(raw_input, model_cls):
        return raw_input

    data = raw_input
    if isinstance(raw_input, str):
        try:
            cleaned_str = raw_input.strip()
            if cleaned_str.startswith("```json"):
                cleaned_str = cleaned_str[7:]
            elif cleaned_str.startswith("```"):
                cleaned_str = cleaned_str[3:]
            if cleaned_str.endswith("```"):
                cleaned_str = cleaned_str[:-3]
            cleaned_str = cleaned_str.strip()
            data = json.loads(cleaned_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON output string: {e}")
            raise ValueError(f"Invalid JSON string returned by LLM: {raw_input[:100]}...") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected dict or JSON string for {model_cls.__name__}, got {type(data)}")

    # Pre-process & sanitize fields for specific models
    if model_cls == StrategyResult:
        if isinstance(data.get("target_audience_analysis"), (dict, list)):
            data["target_audience_analysis"] = json.dumps(data["target_audience_analysis"])
        if isinstance(data.get("hook_strategy"), (dict, list)):
            data["hook_strategy"] = json.dumps(data["hook_strategy"])
        if isinstance(data.get("format_guidelines"), list):
            sanitized_fg = []
            for item in data["format_guidelines"]:
                if isinstance(item, dict):
                    sanitized_fg.append(", ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    sanitized_fg.append(str(item))
            data["format_guidelines"] = sanitized_fg
    elif model_cls == ResearchResult:
        for field_name in ["summary"]:
            if isinstance(data.get(field_name), (dict, list)):
                data[field_name] = json.dumps(data[field_name])
        for list_field in ["key_points", "statistics", "sources", "competitor_analysis", "hooks", "warnings"]:
            if isinstance(data.get(list_field), list):
                data[list_field] = [json.dumps(x) if isinstance(x, (dict, list)) else str(x) for x in data[list_field]]
    elif model_cls == ScriptResult:
        for str_field in ["hook", "body", "cta"]:
            if isinstance(data.get(str_field), (dict, list)):
                data[str_field] = json.dumps(data[str_field])

    try:
        return model_cls.model_validate(data)
    except ValidationError as ve:
        logger.warning(f"Validation error parsing {model_cls.__name__}: {ve}")
        raise ValueError(f"LLM output failed schema contract for {model_cls.__name__}: {ve}") from ve
