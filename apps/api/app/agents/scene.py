from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.ai_contracts import ScenePlan, validate_ai_response
from app.visual.continuity import (
    CharacterAnchor,
    EnvironmentAnchor,
    SceneContinuity,
    VisualBible,
    VisualContinuityEngine,
)
import json


class SceneAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are a cinematic scene planner and continuity supervisor for short-form videos.
Break down the provided script into 3 to 5 scenes. Plan the video as one continuous
world, not as unrelated images.

Return ONLY valid JSON with this structure:
{
  "visual_bible": {
    "style": "cinematic visual style and period-appropriate visual language",
    "characters": [
      {
        "character_id": "CHAR_01",
        "description": "specific stable face, age range, hair, skin tone and body build",
        "wardrobe": "specific clothing and accessories that remain unchanged",
        "persistent_features": ["distinctive features that must not drift"]
      }
    ],
    "environments": [
      {
        "environment_id": "LOC_01",
        "description": "specific architecture, geography and layout",
        "lighting": "time of day, weather and stable lighting",
        "persistent_layout": ["landmarks and spatial relationships that remain fixed"]
      }
    ],
    "prop_anchors": ["important objects and which hand/location they remain in"],
    "global_constraints": ["historical and visual constraints shared by all scenes"]
  },
  "scenes": [
    {
      "scene_number": 1,
      "duration": 3.5,
      "narration": "What is said in this scene",
      "visual_description": "What we see and the action taking place",
      "visual_prompt": "Detailed cinematic image/video prompt",
      "continuity_state": {
        "time_position": "chronological position",
        "character_positions": ["CHAR_01 starts frame left, facing the gate"],
        "action_state": "precise action and its current stage",
        "prop_state": ["sword remains in CHAR_01's right hand"],
        "screen_direction": "movement direction and axis",
        "camera_setup": "shot size, lens feel, angle and camera movement",
        "transition_in": "how this shot follows the prior shot",
        "transition_out": "how this shot leads to the next"
      },
      "onscreen_text": "Text to display",
      "transition": "none",
      "sound_effect": "whoosh"
    }
  ]
}

Rules:
- Reuse the same character IDs, face descriptions, wardrobe and accessories in every scene.
- Reuse environment IDs and preserve geography, architecture, object positions, weather and lighting
  unless the story explicitly changes them.
- Actions must be physically plausible: clear contact, balance, weight, momentum, gravity and cause/effect.
- Specify where people and props are before and after important actions. Avoid teleporting or changing hands.
- Preserve screen direction and the 180-degree axis unless a deliberate motivated camera move is described.
- Vary shot sizes and camera movement for cinematic coverage, but keep spatial geography legible.
- Choose a coherent director style (documentary, epic historical cinema, thriller, action, emotional drama)
  appropriate to the story. Do not sacrifice continuity for visual variety.
- For historical scenes, avoid anachronistic clothing, tools, architecture and materials.
- If a scene has no recurring human character, use an empty characters list rather than inventing one.
"""

    async def plan_scenes(self, script_data: dict) -> ScenePlan:
        await log_manager.broadcast("Planning scenes and visual continuity bible...", agent="SceneAgent")
        user_prompt = f"Script Data: {json.dumps(script_data)}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        validated = validate_ai_response(raw_res, ScenePlan)

        bible_data = validated.visual_bible or {}
        characters = [
            CharacterAnchor(
                character_id=item.get("character_id", f"CHAR_{index + 1:02d}"),
                description=item.get("description", ""),
                wardrobe=item.get("wardrobe", ""),
                persistent_features=item.get("persistent_features", []),
            )
            for index, item in enumerate(bible_data.get("characters", []))
        ]
        environments = [
            EnvironmentAnchor(
                environment_id=item.get("environment_id", f"LOC_{index + 1:02d}"),
                description=item.get("description", ""),
                lighting=item.get("lighting", ""),
                persistent_layout=item.get("persistent_layout", []),
            )
            for index, item in enumerate(bible_data.get("environments", []))
        ]
        bible = VisualBible(
            style=bible_data.get("style", "cinematic naturalism"),
            characters=characters,
            environments=environments,
            prop_anchors=bible_data.get("prop_anchors", []),
            global_constraints=bible_data.get("global_constraints", []),
        )
        engine = VisualContinuityEngine(bible)
        previous_state = None
        for scene in sorted(validated.scenes, key=lambda item: item.scene_number):
            state_data = scene.continuity_state or {}
            current_state = SceneContinuity(
                scene_number=scene.scene_number,
                time_position=state_data.get("time_position", ""),
                character_positions=state_data.get("character_positions", []),
                action_state=state_data.get("action_state", scene.visual_description or scene.narration),
                prop_state=state_data.get("prop_state", []),
                screen_direction=state_data.get("screen_direction", ""),
                camera_setup=state_data.get("camera_setup", ""),
                transition_in=state_data.get("transition_in", ""),
                transition_out=state_data.get("transition_out", ""),
            )
            scene.visual_prompt = engine.build_prompt(
                scene.visual_prompt or scene.visual_description,
                scene.scene_number,
                previous_scene=previous_state,
                current_scene=current_state,
            )
            previous_state = current_state

        await log_manager.broadcast(
            f"Planned {len(validated.scenes)} scenes with shared visual identity and continuity constraints.",
            agent="SceneAgent",
        )
        return validated
