from app.agents.base import BaseAgent
from app.core.logging import log_manager
import json

class SceneAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are a Scene Planner for short-form videos.
Break down the provided script into 3 to 5 scenes.
Return ONLY valid JSON with this structure:
{
    "scenes": [
        {
            "scene_number": 1,
            "duration": 3.5,
            "narration": "What is said in this scene",
            "visual_description": "What we see",
            "visual_prompt": "A prompt for an image generator",
            "onscreen_text": "Text to display",
            "transition": "none",
            "sound_effect": "whoosh"
        }
    ]
}
"""

    async def plan_scenes(self, script_data: dict) -> dict:
        await log_manager.broadcast("Breaking script down into scenes...", agent="SceneAgent")
        user_prompt = f"Script Data: {json.dumps(script_data)}"
        result = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        await log_manager.broadcast(f"Planned {len(result.get('scenes', []))} scenes successfully.", agent="SceneAgent")
        return result
