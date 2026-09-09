from typing import List
from pydantic import BaseModel, Field
from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.ai_contracts import validate_ai_response
import json

class BatchVariation(BaseModel):
    title: str = Field(..., description="Distinct video title")
    angle: str = Field(..., description="Creative angle (e.g. Explainer, Contrarian, Case Study, Top 5)")
    target_audience: str = Field(default="General Tech Enthusiasts")
    format_style: str = Field(default="Fast-paced Short")

class BatchStrategyResult(BaseModel):
    topic: str
    variations: List[BatchVariation] = Field(..., min_length=1)

class BatchStrategyAgent(BaseAgent):
    SYSTEM_PROMPT = """
You are an expert Content Strategy Director.
Given a topic and requested count, generate distinct, highly strategic creative angles for a video batch.
Do NOT just generate 'Variation 1', 'Variation 2'.
Instead, use unique angles such as:
- Beginner Explainer
- Contrarian Hot Take
- Top 5 Practical Tips
- Case Study / Real World Success
- Myth vs Reality
- Future Predictions (2026+)
- Deep Dive Step-by-Step

Return ONLY valid JSON with this format:
{
    "topic": "Topic Name",
    "variations": [
        {
            "title": "Title for video 1",
            "angle": "Contrarian Hot Take",
            "target_audience": "Software Developers",
            "format_style": "High-energy pattern interrupt"
        }
    ]
}
"""

    async def generate_batch_plan(self, topic: str, count: int = 3, platform: str = "Shorts") -> BatchStrategyResult:
        await log_manager.broadcast(f"Formulating {count} distinct strategic angles for topic batch '{topic}'...", agent="BatchStrategyAgent")
        user_prompt = f"Topic: {topic}\nCount: {count}\nPlatform: {platform}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        validated = validate_ai_response(raw_res, BatchStrategyResult)
        await log_manager.broadcast(f"Generated {len(validated.variations)} strategic batch angles for '{topic}'", agent="BatchStrategyAgent")
        return validated
