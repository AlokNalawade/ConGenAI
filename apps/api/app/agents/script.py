from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.ai_contracts import ScriptResult, validate_ai_response
import json

class ScriptAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are an expert Scriptwriter for short-form video content.
Based on the provided research, generate a highly engaging script.
Return ONLY valid JSON with the following structure:
{
    "hook": "The first 3 seconds to grab attention",
    "body": "The main script content",
    "cta": "Call to action at the end",
    "estimated_duration": 45,
    "word_count": 120
}
"""

    async def generate_script(self, research_data: dict, platform: str = "Shorts") -> ScriptResult:
        await log_manager.broadcast(f"Writing script based on research for {platform}...", agent="ScriptAgent")
        user_prompt = f"Platform: {platform}\nResearch Data: {json.dumps(research_data)}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        validated = validate_ai_response(raw_res, ScriptResult)
        await log_manager.broadcast(f"Script generated! Estimated duration: {validated.estimated_duration}s", agent="ScriptAgent")
        return validated

