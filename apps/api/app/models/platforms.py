"""Platform Adaptation Models and Specifications (Buffer-style).

Defines platform-native constraints and structural requirements:
- YouTube Longform (16:9, deep chapters, high-retention structure)
- YouTube Shorts (9:16, 30-50s, loopable end-screen, subscribe CTA)
- Instagram Reels (9:16, 20-45s, aesthetic visuals, share/save CTA, hashtag clusters)
- TikTok (9:16, 25-40s, raw tone, conversational hook, comment question)
- LinkedIn (1:1 / 4:5 video or carousel slides, executive thought leadership)
- X / Twitter (16:9 teaser clip + 5-7 tweet hook thread)
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SocialPlatform(str, Enum):
    YOUTUBE_LONG = "youtube_long"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    X_THREAD = "x_thread"


class PlatformSpec(BaseModel):
    """Platform-specific technical and editorial constraints."""
    platform: SocialPlatform
    display_name: str
    aspect_ratio: str
    width: int
    height: int
    target_duration_seconds: int
    max_duration_seconds: int
    pacing_wpm: int = 150  # Words per minute
    caption_max_chars: int
    optimal_hashtag_count: int
    preferred_cta_type: str
    description_structure: str


PLATFORM_SPECS: Dict[SocialPlatform, PlatformSpec] = {
    SocialPlatform.YOUTUBE_SHORTS: PlatformSpec(
        platform=SocialPlatform.YOUTUBE_SHORTS,
        display_name="YouTube Shorts",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        target_duration_seconds=45,
        max_duration_seconds=60,
        pacing_wpm=160,
        caption_max_chars=100,
        optimal_hashtag_count=3,
        preferred_cta_type="subscribe_channel",
        description_structure="Punchy 1-line hook + 3 targeted hashtags + channel link",
    ),
    SocialPlatform.INSTAGRAM_REELS: PlatformSpec(
        platform=SocialPlatform.INSTAGRAM_REELS,
        display_name="Instagram Reels",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        target_duration_seconds=35,
        max_duration_seconds=90,
        pacing_wpm=155,
        caption_max_chars=2200,
        optimal_hashtag_count=5,
        preferred_cta_type="save_and_share",
        description_structure="Headline + 3 key takeaways + Save this for later CTA + 5 hashtags",
    ),
    SocialPlatform.TIKTOK: PlatformSpec(
        platform=SocialPlatform.TIKTOK,
        display_name="TikTok",
        aspect_ratio="9:16",
        width=1080,
        height=1920,
        target_duration_seconds=30,
        max_duration_seconds=60,
        pacing_wpm=170,
        caption_max_chars=2200,
        optimal_hashtag_count=4,
        preferred_cta_type="comment_debate",
        description_structure="Controversial question + 4 trending hashtags",
    ),
    SocialPlatform.LINKEDIN: PlatformSpec(
        platform=SocialPlatform.LINKEDIN,
        display_name="LinkedIn Post & Carousel",
        aspect_ratio="1:1",
        width=1080,
        height=1080,
        target_duration_seconds=60,
        max_duration_seconds=300,
        pacing_wpm=140,
        caption_max_chars=3000,
        optimal_hashtag_count=3,
        preferred_cta_type="comment_thoughts",
        description_structure="Problem statement -> 3 bullet insight framework -> Discussion question",
    ),
    SocialPlatform.X_THREAD: PlatformSpec(
        platform=SocialPlatform.X_THREAD,
        display_name="X / Twitter Thread",
        aspect_ratio="16:9",
        width=1280,
        height=720,
        target_duration_seconds=40,
        max_duration_seconds=140,
        pacing_wpm=160,
        caption_max_chars=280,
        optimal_hashtag_count=1,
        preferred_cta_type="retweet_and_follow",
        description_structure="High-curiosity hook tweet + 1/X thread structure + teaser clip",
    ),
    SocialPlatform.YOUTUBE_LONG: PlatformSpec(
        platform=SocialPlatform.YOUTUBE_LONG,
        display_name="YouTube Longform",
        aspect_ratio="16:9",
        width=1920,
        height=1080,
        target_duration_seconds=480,
        max_duration_seconds=1200,
        pacing_wpm=145,
        caption_max_chars=5000,
        optimal_hashtag_count=3,
        preferred_cta_type="subscribe_and_bell",
        description_structure="Executive summary + Timestamps / Chapters + Resources + Socials",
    ),
}


class PlatformAdaptedContent(BaseModel):
    """An adaptation of a master story tailored for a specific platform."""
    platform: SocialPlatform
    title: str
    hook: str
    script: str
    target_duration: int
    aspect_ratio: str
    caption: str
    hashtags: List[str]
    cta: str
    thread_tweets: Optional[List[str]] = None  # For X / Twitter threads
    carousel_slides: Optional[List[str]] = None  # For LinkedIn carousels
    metadata: Dict[str, Any] = Field(default_factory=dict)
