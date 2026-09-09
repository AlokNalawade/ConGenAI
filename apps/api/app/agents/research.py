from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.ai_contracts import ResearchResult, validate_ai_response

class ResearchAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are an expert Content Researcher for social media platforms (TikTok, Instagram Reels, YouTube Shorts).
Your task is to take a content idea and generate a structured research package.
Return ONLY valid JSON with the following structure:
{
    "summary": "Brief summary of the research",
    "key_points": ["point 1", "point 2", "point 3"],
    "statistics": ["stat 1", "stat 2"],
    "sources": ["source 1"],
    "competitor_analysis": ["insight 1", "insight 2"],
    "hooks": ["hook 1", "hook 2", "hook 3"],
    "warnings": ["controversial point to avoid"]
}
"""

    async def research_topic(self, topic: str, target_audience: str = "General", platform: str = "Shorts") -> ResearchResult:
        await log_manager.broadcast(f"Initiating research protocol for topic: '{topic}'", agent="ResearchAgent")
        user_prompt = f"Topic: {topic}\nTarget Audience: {target_audience}\nPlatform: {platform}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        validated = validate_ai_response(raw_res, ResearchResult)
        return validated

