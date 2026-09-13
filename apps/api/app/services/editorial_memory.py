"""Editorial Memory & Taste Learning Loop.

Captures human corrections (edited hooks, rejected visuals, voice feedback)
and builds a persistent creator taste profile that dynamically enriches future agent prompts:
- Hook preferences (e.g. Contrarian vs Question vs Story)
- Visual style constraints (e.g. Reject generic stock art, prefer dark tech diagrams)
- Voice cadence & energy adjustments
- Negative phrase blacklists
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class FeedbackCategory(str, Enum):
    HOOK = "hook"
    VISUAL = "visual"
    VOICE = "voice"
    SCRIPT = "script"
    PACING = "pacing"


class FeedbackEvent(BaseModel):
    category: FeedbackCategory
    original_value: Optional[str] = None
    corrected_value: Optional[str] = None
    rejection_reason: Optional[str] = None
    context_topic: Optional[str] = None


class EditorialTasteProfile(BaseModel):
    preferred_hook_styles: List[str] = Field(default_factory=lambda: ["Contrarian", "Curiosity gap"])
    banned_visual_tropes: List[str] = Field(default_factory=lambda: ["Generic stock office photos", "Cartoonish 3D figures"])
    voice_guidance: List[str] = Field(default_factory=lambda: ["Natural conversational tone", "Avoid robotic cadence"])
    banned_phrases: List[str] = Field(default_factory=lambda: ["game changer", "revolutionary", "in this video"])
    total_feedback_count: int = 0


class EditorialMemoryService:
    _instance = None
    _profile = EditorialTasteProfile()
    _events: List[FeedbackEvent] = []

    @classmethod
    def get_instance(cls) -> "EditorialMemoryService":
        if cls._instance is None:
            cls._instance = EditorialMemoryService()
        return cls._instance

    def record_hook_correction(self, original_hook: str, user_hook: str, topic: Optional[str] = None):
        """Record when a creator overrides an AI-generated hook."""
        event = FeedbackEvent(
            category=FeedbackCategory.HOOK,
            original_value=original_hook,
            corrected_value=user_hook,
            context_topic=topic,
        )
        self._events.append(event)
        self._profile.total_feedback_count += 1
        
        # Learn from contrast
        if any(w in user_hook.lower() for w in ["why", "stop", "fail", "useless", "broke", "never"]):
            if "Contrarian / High-conflict" not in self._profile.preferred_hook_styles:
                self._profile.preferred_hook_styles.append("Contrarian / High-conflict")

    def record_visual_rejection(self, reason: str, topic: Optional[str] = None):
        """Record when a visual is rejected and update negative prompt constraints."""
        event = FeedbackEvent(
            category=FeedbackCategory.VISUAL,
            rejection_reason=reason,
            context_topic=topic,
        )
        self._events.append(event)
        self._profile.total_feedback_count += 1
        if reason and reason not in self._profile.banned_visual_tropes:
            self._profile.banned_visual_tropes.append(reason)

    def record_voice_feedback(self, feedback: str):
        """Record adjustments to voice tone or pacing."""
        event = FeedbackEvent(
            category=FeedbackCategory.VOICE,
            rejection_reason=feedback,
        )
        self._events.append(event)
        self._profile.total_feedback_count += 1
        if feedback and feedback not in self._profile.voice_guidance:
            self._profile.voice_guidance.append(feedback)

    def get_editorial_guidelines(self) -> str:
        """Construct prompt injection text containing the creator's learned taste profile."""
        lines = ["--- LEARNED CREATOR EDITORIAL TASTE GUIDELINES ---"]
        if self._profile.preferred_hook_styles:
            lines.append(f"Preferred Hook Styles: {', '.join(self._profile.preferred_hook_styles)}")
        if self._profile.banned_visual_tropes:
            lines.append(f"Banned Visual Tropes (Avoid): {', '.join(self._profile.banned_visual_tropes)}")
        if self._profile.voice_guidance:
            lines.append(f"Voice & Delivery Preferences: {', '.join(self._profile.voice_guidance)}")
        if self._profile.banned_phrases:
            lines.append(f"Strictly Banned Phrasing: {', '.join(self._profile.banned_phrases)}")
        lines.append("--------------------------------------------------")
        return "\n".join(lines)

    def get_profile(self) -> EditorialTasteProfile:
        return self._profile
