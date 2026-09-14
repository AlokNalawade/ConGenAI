"""Hybrid Curated B-Roll Library & Provider (InVideo style).

Provides an instant, high-FPS B-roll selection layer to complement generative AI:
- Curated catalog of high-impact 60fps tech/finance/cyber video loops
- Semantic tag matching against scene narration & visual prompts
- Instant rendering: 0s wait time compared to 30s diffusion generation
"""

import os
import re
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field
from app.core.config import settings


class BRollClip(BaseModel):
    id: str
    name: str
    filename: str
    category: str
    tags: List[str]
    duration: float = 5.0
    aspect_ratio: str = "9:16"
    relevance_score: float = 0.0


# Built-in local library catalog (CC0 / Public Domain loops)
BUILTIN_BROLL_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "broll_server_01",
        "name": "Server Rack Blinking Lights",
        "filename": "datacenter_servers.mp4",
        "category": "infrastructure",
        "tags": ["server", "cloud", "datacenter", "infrastructure", "backend", "hardware", "database", "redis", "postgres"],
    },
    {
        "id": "broll_code_02",
        "name": "Developer Code Terminal",
        "filename": "code_editor_typing.mp4",
        "category": "software",
        "tags": ["code", "coding", "software", "developer", "engineer", "python", "terminal", "algorithm", "build"],
    },
    {
        "id": "broll_cyber_03",
        "name": "Neural Cyber Network Grid",
        "filename": "cyber_network_grid.mp4",
        "category": "ai",
        "tags": ["ai", "agent", "neural", "network", "cyber", "machine learning", "intelligence", "future", "matrix"],
    },
    {
        "id": "broll_finance_04",
        "name": "Financial Candlestick Charts",
        "filename": "financial_candlestick_charts.mp4",
        "category": "finance",
        "tags": ["finance", "money", "profit", "stock", "trading", "crypto", "revenue", "loss", "growth", "market"],
    },
    {
        "id": "broll_abstract_05",
        "name": "Abstract Tech Particles",
        "filename": "abstract_particles_flow.mp4",
        "category": "abstract",
        "tags": ["abstract", "particles", "energy", "speed", "flow", "innovation", "technology", "quantum"],
    },
]


class BRollService:
    # Class-level usage and recency tracking across batches
    _global_usage_counts: Dict[str, int] = {}
    _recent_clips: List[str] = []

    def __init__(self, library_dir: Optional[str] = None):
        self.library_dir = library_dir or os.path.join(settings.ASSETS_DIR, "library", "broll")
        os.makedirs(self.library_dir, exist_ok=True)
        self.catalog = [BRollClip(**item) for item in BUILTIN_BROLL_CATALOG]

    @classmethod
    def reset_usage(cls):
        """Reset usage counts and recency buffer (useful for testing or fresh batches)."""
        cls._global_usage_counts.clear()
        cls._recent_clips.clear()

    @classmethod
    def record_usage(cls, clip_id: str):
        """Record usage of a clip to prevent repetitive selection."""
        cls._global_usage_counts[clip_id] = cls._global_usage_counts.get(clip_id, 0) + 1
        cls._recent_clips.append(clip_id)
        if len(cls._recent_clips) > 10:
            cls._recent_clips.pop(0)

    def match_broll(self, text: str, disallow_recently_used: bool = True) -> Optional[BRollClip]:
        """Find best matching B-roll clip based on keyword overlap and anti-repetition weighting."""
        clean_text = set(re.findall(r"\w+", text.lower()))
        best_clip = None
        highest_score = 0.0

        for clip in self.catalog:
            overlap = len(clean_text.intersection(set(clip.tags)))
            if overlap == 0:
                continue

            base_score = min(1.0, round(overlap / 3.0, 2))
            
            # Anti-repetition penalties
            usage_count = self._global_usage_counts.get(clip.id, 0)
            penalty = 1.0 / (1.0 + 0.5 * usage_count)
            
            # Heavy penalty if clip was used in the immediately preceding scenes
            if disallow_recently_used and self._recent_clips and clip.id == self._recent_clips[-1]:
                penalty *= 0.2
            elif disallow_recently_used and clip.id in self._recent_clips[-3:]:
                penalty *= 0.5

            effective_score = round(base_score * penalty, 2)
            if effective_score > highest_score:
                highest_score = effective_score
                best_clip = clip.model_copy()
                best_clip.relevance_score = effective_score

        return best_clip

    def should_use_broll(self, scene_prompt: str, threshold: float = 0.5, auto_record: bool = True) -> Tuple[bool, Optional[BRollClip]]:
        """Determine if a scene should use instant stock B-roll instead of generating an AI image."""
        matched = self.match_broll(scene_prompt)
        if matched and matched.relevance_score >= threshold:
            if auto_record:
                self.record_usage(matched.id)
            return True, matched
        return False, None
