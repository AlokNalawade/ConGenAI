from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.ai_contracts import StrategyResult, validate_ai_response
import json

class StrategyAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are an expert Content Strategist for viral short-form and long-form digital videos.
Based on research data, formulate a strategy for maximum audience engagement.
Return ONLY valid JSON with the following structure:
{
    "content_angle": "Core perspective or narrative angle",
    "target_audience_analysis": "Key preferences and pain points of the audience",
    "hook_strategy": "Framework used to hook the viewer in 3s (e.g., Pattern Interrupt, Controversy, Curiosity Gap)",
    "format_guidelines": ["Dynamic transitions every 3s", "High energy tone", "Subtitles on screen"]
}
"""

    async def develop_strategy(self, topic: str, research_data: dict, platform: str = "Shorts") -> StrategyResult:
        await log_manager.broadcast(f"Developing content strategy for topic '{topic}' on {platform}...", agent="StrategyAgent")
        user_prompt = f"Topic: {topic}\nPlatform: {platform}\nResearch Data: {json.dumps(research_data)}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        validated = validate_ai_response(raw_res, StrategyResult)
        await log_manager.broadcast(f"Strategy formulated: Angle '{validated.content_angle}', Hook '{validated.hook_strategy}'", agent="StrategyAgent")
        return validated
