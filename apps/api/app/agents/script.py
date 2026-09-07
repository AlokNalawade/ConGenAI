from app.agents.base import BaseAgent
from app.core.logging import log_manager
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

    async def generate_script(self, research_data: dict, platform: str = "Shorts") -> dict:
        await log_manager.broadcast(f"Writing script based on research for {platform}...", agent="ScriptAgent")
        user_prompt = f"Platform: {platform}\nResearch Data: {json.dumps(research_data)}"
        result = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        await log_manager.broadcast(f"Script generated! Estimated duration: {result.get('estimated_duration')}s", agent="ScriptAgent")
        return result
