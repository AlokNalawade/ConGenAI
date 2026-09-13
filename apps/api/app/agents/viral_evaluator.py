"""Pre-Render Viral Potential Scoring Engine.

Evaluates content before rendering to gate expensive media generation cycles:
- Hook Score (1-10): First 1-3 seconds curiosity, pattern interrupt, clarity
- Novelty Score (1-10): Counter-intuitive angle, unique perspective vs generic cliché
- Retention Score (1-10): Pacing, story escalation, open loops, minimal drop-off risk
- Emotional Intensity (1-10): Intellectual curiosity, urgency, surprise
- Overall Composite Score (1-10)

Decision Gating:
- Overall < 7.0: REWRITE_NEEDED (automated feedback loop to ScriptAgent)
- 7.0 - 8.0: APPROVED (standard render queue)
- > 8.0: PRIORITY_RENDER (high-priority queue + viral badge)
"""

import os
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.ai_contracts import validate_ai_response


class ViralDecision(str, Enum):
    REWRITE_NEEDED = "rewrite_needed"
    APPROVED = "approved"
    PRIORITY_RENDER = "priority_render"


class ViralScoreBreakdown(BaseModel):
    hook_score: float = Field(..., ge=1.0, le=10.0, description="Hook effectiveness in first 1-3 seconds")
    novelty_score: float = Field(..., ge=1.0, le=10.0, description="Uniqueness and non-obvious angle")
    retention_score: float = Field(..., ge=1.0, le=10.0, description="Anticipated watch time and narrative pacing")
    emotional_intensity: float = Field(..., ge=1.0, le=10.0, description="Curiosity, urgency, or intellectual resonance")
    overall_score: float = Field(..., ge=1.0, le=10.0, description="Weighted composite score")
    
    decision: ViralDecision
    hook_critique: str
    pacing_critique: str
    actionable_improvements: List[str] = Field(default_factory=list)


class ViralEvaluatorAgent(BaseAgent):
    SYSTEM_PROMPT = """You are a Ruthless Viral Content Editor & Retention Analyst for TikTok, Reels, and Shorts.
Critique the provided title, hook, and full script.
Score strictly on a 1.0 to 10.0 scale across:
1. hook_score: Does it immediately interrupt the feed in the first 2 seconds? Is there a curiosity gap?
2. novelty_score: Is this fresh, or is it obvious ChatGPT cliché fluff?
3. retention_score: Does the story accelerate? Are there open loops? Is pacing brisk?
4. emotional_intensity: Does the viewer feel urgency, surprise, or desire to save/share?

Calculate overall_score as: (0.35 * hook) + (0.30 * retention) + (0.20 * novelty) + (0.15 * emotional)

Decision rules:
- overall_score < 7.0: "rewrite_needed"
- 7.0 <= overall_score <= 8.0: "approved"
- overall_score > 8.0: "priority_render"

Return ONLY valid JSON matching this schema:
{
    "hook_score": 8.7,
    "novelty_score": 7.9,
    "retention_score": 9.1,
    "emotional_intensity": 8.0,
    "overall_score": 8.6,
    "decision": "priority_render",
    "hook_critique": "High contrast hook creates an immediate open loop.",
    "pacing_critique": "Crisp transitions between scenes without filler words.",
    "actionable_improvements": ["Trim 2 words from sentence 3", "Elevate closing CTA"]
}"""

    async def evaluate_script(
        self,
        title: str,
        hook: str,
        script_text: str,
        target_duration: int = 45,
    ) -> ViralScoreBreakdown:
        """Score content viral potential prior to media generation."""
        await log_manager.broadcast(f"Evaluating Viral Potential for '{title}'...", agent="ViralEvaluatorAgent")

        if os.getenv("TESTING") or os.getenv("DEV_MODE"):
            # If script has contrarian or specific hook cues, give high score; else moderate
            is_high = any(w in hook.lower() for w in ["stop", "why", "truth", "broke", "90%", "never"])
            if is_high:
                hook_s = 8.8
                nov_s = 8.1
                ret_s = 8.9
                emo_s = 8.0
                decision = ViralDecision.PRIORITY_RENDER
            elif "rewrite" in script_text.lower():
                hook_s = 5.2
                nov_s = 5.0
                ret_s = 5.8
                emo_s = 4.9
                decision = ViralDecision.REWRITE_NEEDED
            else:
                hook_s = 7.5
                nov_s = 7.2
                ret_s = 7.6
                emo_s = 7.3
                decision = ViralDecision.APPROVED

            overall = round((0.35 * hook_s) + (0.30 * ret_s) + (0.20 * nov_s) + (0.15 * emo_s), 1)
            return ViralScoreBreakdown(
                hook_score=hook_s,
                novelty_score=nov_s,
                retention_score=ret_s,
                emotional_intensity=emo_s,
                overall_score=overall,
                decision=decision,
                hook_critique="Pattern interrupt effectively captures early attention." if overall >= 7.0 else "Hook is too passive and lacks an immediate curiosity gap.",
                pacing_critique="Fast information delivery with concise scene steps." if overall >= 7.0 else "Middle section lags with redundant adjectives.",
                actionable_improvements=["Sharpen first 5 words", "Ensure end CTA poses an explicit engagement question"] if overall < 7.0 else [],
            )

        user_prompt = f"Title: {title}\nHook: {hook}\nTarget Duration: {target_duration}s\nFull Script:\n{script_text}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        return validate_ai_response(raw_res, ViralScoreBreakdown)
