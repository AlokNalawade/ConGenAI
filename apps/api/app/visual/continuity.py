"""Deterministic visual-continuity helpers for scene prompt construction.

This module does not generate images or claim to guarantee model adherence. It
turns a scene plan into prompts that explicitly carry identity, spatial,
temporal, physical-motion and cinematography constraints across shots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class CharacterAnchor:
    character_id: str
    description: str
    wardrobe: str = ""
    persistent_features: list[str] = field(default_factory=list)

    def render(self) -> str:
        details = [self.description.strip()]
        if self.wardrobe:
            details.append(f"Wardrobe: {self.wardrobe.strip()}")
        if self.persistent_features:
            details.append("Unchanging features: " + ", ".join(self.persistent_features))
        return f"{self.character_id}: " + "; ".join(x for x in details if x)


@dataclass
class EnvironmentAnchor:
    environment_id: str
    description: str
    lighting: str = ""
    persistent_layout: list[str] = field(default_factory=list)

    def render(self) -> str:
        details = [self.description.strip()]
        if self.lighting:
            details.append(f"Lighting/time: {self.lighting.strip()}")
        if self.persistent_layout:
            details.append("Layout anchors: " + ", ".join(self.persistent_layout))
        return f"{self.environment_id}: " + "; ".join(x for x in details if x)


@dataclass
class VisualBible:
    """Stable visual facts shared by every scene in one content run."""

    style: str = "cinematic naturalism"
    characters: list[CharacterAnchor] = field(default_factory=list)
    environments: list[EnvironmentAnchor] = field(default_factory=list)
    prop_anchors: list[str] = field(default_factory=list)
    global_constraints: list[str] = field(default_factory=list)

    def render(self) -> str:
        sections = [f"GLOBAL VISUAL STYLE: {self.style}"]
        if self.characters:
            sections.append("CHARACTER IDENTITY LOCK:\n" + "\n".join(x.render() for x in self.characters))
        if self.environments:
            sections.append("ENVIRONMENT LOCK:\n" + "\n".join(x.render() for x in self.environments))
        if self.prop_anchors:
            sections.append("PERSISTENT PROPS: " + "; ".join(self.prop_anchors))
        if self.global_constraints:
            sections.append("PROJECT CONSTRAINTS: " + "; ".join(self.global_constraints))
        return "\n\n".join(sections)


@dataclass
class SceneContinuity:
    scene_number: int
    time_position: str = ""
    character_positions: list[str] = field(default_factory=list)
    action_state: str = ""
    prop_state: list[str] = field(default_factory=list)
    screen_direction: str = ""
    camera_setup: str = ""
    transition_in: str = ""
    transition_out: str = ""

    def render(self) -> str:
        parts = [f"SCENE {self.scene_number} CONTINUITY STATE"]
        for label, value in (
            ("Chronology", self.time_position),
            ("Action state", self.action_state),
            ("Screen direction", self.screen_direction),
            ("Camera", self.camera_setup),
            ("Incoming transition", self.transition_in),
            ("Outgoing transition", self.transition_out),
        ):
            if value:
                parts.append(f"{label}: {value}")
        parts.extend(f"Character position: {x}" for x in self.character_positions)
        parts.extend(f"Prop state: {x}" for x in self.prop_state)
        return "\n".join(parts)


class VisualContinuityEngine:
    """Build continuity-aware prompts without binding to a specific image model."""

    PHYSICALITY = (
        "PHYSICAL REALISM: preserve believable anatomy, balance, weight, gravity, "
        "inertia and contact. Feet must meet the ground; objects must be supported; "
        "actions must have clear cause and effect. Avoid floating, sliding, clipping, "
        "teleporting, impossible joints and contradictory motion."
    )
    CAMERA = (
        "CINEMATOGRAPHY: use intentional framing, plausible lens perspective, "
        "motivated camera movement, coherent screen direction, natural depth of field "
        "and lighting consistent with the established time and environment."
    )
    CONTINUITY = (
        "SHOT CONTINUITY: recurring people retain the same face, age, hair, skin tone, "
        "body proportions, wardrobe and accessories. Keep architecture, geography, "
        "weather, lighting, object placement and damage states stable unless the story "
        "explicitly changes them. Preserve left/right screen direction and action "
        "progression between adjacent shots."
    )

    def __init__(self, bible: Optional[VisualBible] = None):
        self.bible = bible or VisualBible()

    def build_prompt(
        self,
        visual_prompt: str,
        scene_number: int,
        previous_scene: Optional[SceneContinuity] = None,
        current_scene: Optional[SceneContinuity] = None,
    ) -> str:
        sections = [visual_prompt.strip(), self.bible.render(), self.CONTINUITY,
                    self.PHYSICALITY, self.CAMERA]
        if previous_scene:
            sections.append("PREVIOUS SHOT STATE (continue, do not reset):\n" + previous_scene.render())
        if current_scene:
            if current_scene.scene_number != scene_number:
                raise ValueError("current_scene.scene_number must match scene_number")
            sections.append(current_scene.render())
        return "\n\n".join(x for x in sections if x)

    def apply_to_scenes(self, scenes: Iterable[object]) -> None:
        """Enrich scene visual prompts in place; safe for existing Scene contracts."""
        ordered = sorted(scenes, key=lambda item: item.scene_number)
        previous = None
        for scene in ordered:
            scene.visual_prompt = self.build_prompt(
                scene.visual_prompt or scene.visual_description,
                scene.scene_number,
                previous_scene=previous,
            )
            previous = SceneContinuity(
                scene_number=scene.scene_number,
                action_state=(scene.visual_description or scene.narration or "")[:500],
            )
