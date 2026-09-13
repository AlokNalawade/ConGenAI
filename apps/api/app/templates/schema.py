"""Creatomate-style Multi-Track Composition Schema for ConGenAI.

Defines a structured, deterministic composition model for video rendering.
Instead of simple sequential scenes, a composition supports multi-layered tracks:
- Hook layer (pattern interrupt, badge, sound effect)
- Main visual layer (image/video, pan/zoom Ken Burns, fit/fill)
- Headline layer (persistent top banner, dynamic chapter headings)
- Subtitle layer (karaoke or block text, word highlights)
- B-Roll / Overlay layer (picture-in-picture, split screen)
- Voice & Background Music layers (with auto-ducking)
- Progress Indicator layer (linear bar, timer countdown)
- Call-to-Action (CTA) & Outro card layers
"""

import uuid
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TrackType(str, Enum):
    HOOK = "hook"
    MAIN_VISUAL = "main_visual"
    HEADLINE = "headline"
    SUBTITLES = "subtitles"
    B_ROLL = "b_roll"
    VOICE = "voice"
    BACKGROUND_MUSIC = "background_music"
    PROGRESS_INDICATOR = "progress_indicator"
    CTA = "cta"
    OUTRO = "outro"


class AnimationType(str, Enum):
    NONE = "none"
    FADE = "fade"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    POP = "pop"
    KEN_BURNS = "ken_burns"


class ProgressIndicatorStyle(str, Enum):
    NONE = "none"
    BOTTOM_BAR = "bottom_bar"
    TOP_BAR = "top_bar"
    COUNTDOWN_TIMER = "countdown_timer"


class TemplateElement(BaseModel):
    """An individual element inside a composition track."""
    id: str = Field(default_factory=lambda: f"elem_{uuid.uuid4().hex[:6]}")
    track_type: TrackType
    start_time: float = 0.0
    duration: float = 5.0
    z_index: int = 1
    
    # Visual coordinates & dimensions (in % of canvas, 0-100)
    x: float = 0.0
    y: float = 0.0
    width: float = 100.0
    height: float = 100.0
    
    # Content references
    content_text: Optional[str] = None
    asset_path: Optional[str] = None
    
    # Styling & Animation
    animation: AnimationType = AnimationType.NONE
    font_family: str = "Inter"
    font_size: int = 42
    font_color: str = "#FFFFFF"
    background_color: Optional[str] = None
    opacity: float = 1.0
    volume: float = 1.0
    custom_props: Dict[str, Any] = Field(default_factory=dict)


class CompositionScene(BaseModel):
    """A scene in the composition containing layered elements."""
    scene_number: int
    duration: float
    headline: Optional[str] = None
    narration: Optional[str] = None
    visual_description: Optional[str] = None
    image_path: Optional[str] = None
    audio_path: Optional[str] = None
    b_roll_path: Optional[str] = None
    elements: List[TemplateElement] = Field(default_factory=list)


class ContentComposition(BaseModel):
    """Full programmatic specification of a video composition."""
    id: str = Field(default_factory=lambda: f"comp_{uuid.uuid4().hex[:8]}")
    title: str
    template_variant: str = "fast_news_explainer"
    aspect_ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    fps: int = 25
    total_duration: float = 0.0
    
    # Global layers
    progress_style: ProgressIndicatorStyle = ProgressIndicatorStyle.BOTTOM_BAR
    progress_color: str = "#FF4444"
    background_music_path: Optional[str] = None
    music_volume: float = 0.15
    auto_ducking: bool = True
    
    # Outro / CTA
    cta_text: Optional[str] = "Follow for daily AI breakdowns"
    cta_handle: Optional[str] = "@congenai"
    outro_duration: float = 2.5
    
    # Scenes
    scenes: List[CompositionScene] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TemplatePreset(BaseModel):
    """A predefined template blueprint with default styling and track configuration."""
    name: str
    display_name: str
    description: str
    aspect_ratio: str = "9:16"
    width: int = 1080
    height: int = 1920
    default_progress_style: ProgressIndicatorStyle
    default_progress_color: str
    headline_font: str
    headline_bg: Optional[str]
    subtitle_style: str
    animation: AnimationType


TEMPLATE_PRESETS: Dict[str, TemplatePreset] = {
    "fast_news_explainer": TemplatePreset(
        name="fast_news_explainer",
        display_name="Fast News Explainer",
        description="High-velocity news format with sticky headline banner, karaoke captions, and bottom progress bar.",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        default_progress_style=ProgressIndicatorStyle.BOTTOM_BAR,
        default_progress_color="#FF3B30",
        headline_font="Inter-Bold",
        headline_bg="#1C1C1E",
        subtitle_style="karaoke_yellow",
        animation=AnimationType.KEN_BURNS,
    ),
    "hormozi_bold": TemplatePreset(
        name="hormozi_bold",
        display_name="Hormozi Bold",
        description="High-retention viral style with giant yellow/white text, punchy transitions, and dynamic countdown.",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        default_progress_style=ProgressIndicatorStyle.TOP_BAR,
        default_progress_color="#FFCC00",
        headline_font="Impact",
        headline_bg=None,
        subtitle_style="bold_yellow",
        animation=AnimationType.POP,
    ),
    "minimal_tech": TemplatePreset(
        name="minimal_tech",
        display_name="Minimalist Tech",
        description="Sleek, dark-mode tech aesthetic with understated progress line and clean typography.",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        default_progress_style=ProgressIndicatorStyle.BOTTOM_BAR,
        default_progress_color="#007AFF",
        headline_font="Inter-Medium",
        headline_bg="#000000",
        subtitle_style="clean_white",
        animation=AnimationType.FADE,
    ),
    "cinematic_documentary": TemplatePreset(
        name="cinematic_documentary",
        display_name="Cinematic Documentary",
        description="Widescreen or cinematic 9:16 with letterbox framing, subtle zoom, and elegant lower-thirds.",
        aspect_ratio="16:9",
        width=1920,
        height=1080,
        default_progress_style=ProgressIndicatorStyle.NONE,
        default_progress_color="#FFFFFF",
        headline_font="Cinzel",
        headline_bg=None,
        subtitle_style="serif_elegant",
        animation=AnimationType.KEN_BURNS,
    ),
}
