"""Repurpose Agent.

Mines long-form source documents (YouTube transcripts, podcasts, research articles)
for high-signal claims, quotes, and moments, producing derived short-form concepts:
- Key takeaway moments
- Empirical claims and statistics
- Multiple standalone viral shorts (Short 1, Short 2, Short 3...)
"""

import os
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.services.source_ingestion import SourceDocument
from app.models.ai_contracts import validate_ai_response


class ExtractedMoment(BaseModel):
    headline: str
    quote_or_claim: str
    significance: str
    target_emotion: str


class DerivedShortConcept(BaseModel):
    concept_id: str = Field(default_factory=lambda: f"short_{uuid.uuid4().hex[:6]}")
    title: str
    hook: str
    core_insight: str
    suggested_duration: int = 45
    suggested_platform: str = "youtube_shorts"
    source_reference: str


import uuid


class RepurposingPlan(BaseModel):
    source_title: str
    overall_summary: str
    key_moments: List[ExtractedMoment]
    derived_shorts: List[DerivedShortConcept]


class RepurposeAgent(BaseAgent):
    SYSTEM_PROMPT = """You are an Expert Content Repurposing Director.
Analyze the provided long-form source material.
1. Extract 2-4 high-impact moments or empirical claims.
2. Produce 3 distinct short-form video concepts (Short 1, Short 2, Short 3).
Each derived short MUST focus on a distinct, punchy angle from the source with a pattern-interrupt hook.

Return ONLY valid JSON matching this schema:
{
    "source_title": "...",
    "overall_summary": "...",
    "key_moments": [
        {
            "headline": "...",
            "quote_or_claim": "...",
            "significance": "...",
            "target_emotion": "..."
        }
    ],
    "derived_shorts": [
        {
            "title": "...",
            "hook": "...",
            "core_insight": "...",
            "suggested_duration": 45,
            "suggested_platform": "youtube_shorts",
            "source_reference": "..."
        }
    ]
}"""

    async def repurpose(
        self,
        doc: SourceDocument,
        short_count: int = 3,
    ) -> RepurposingPlan:
        """Mine long-form source document and generate derived short concepts."""
        await log_manager.broadcast(
            f"Repurposing source '{doc.title}' ({doc.word_count} words) into {short_count} shorts...",
            agent="RepurposeAgent",
        )

        if os.getenv("TESTING") or os.getenv("DEV_MODE"):
            moments = [
                ExtractedMoment(
                    headline="The Operational Bottleneck",
                    quote_or_claim="90% of failures happen in unhandled background task serialization.",
                    significance="Reveals the hidden infrastructure flaw in naive AI pipelines.",
                    target_emotion="Intellectual shock",
                ),
                ExtractedMoment(
                    headline="The 10x Throughput Pattern",
                    quote_or_claim="B-tree indexing and bounded concurrency reduced database deadlocks by 100%.",
                    significance="Clear tactical blueprint for production reliability.",
                    target_emotion="Curiosity & relief",
                ),
            ]
            shorts = [
                DerivedShortConcept(
                    title=f"The Truth About {doc.title}",
                    hook="Everyone thinks AI pipelines crash because of LLM limits. They are completely wrong.",
                    core_insight="The real bottleneck is queue management and database lock contention.",
                    suggested_duration=45,
                    suggested_platform="youtube_shorts",
                    source_reference=doc.title,
                ),
                DerivedShortConcept(
                    title=f"How We Scaled {doc.title}",
                    hook="If your worker queue is running in production, check this one setting immediately.",
                    core_insight="Always commit database jobs before dispatching to Redis.",
                    suggested_duration=40,
                    suggested_platform="tiktok",
                    source_reference=doc.title,
                ),
                DerivedShortConcept(
                    title=f"3 Architecture Rules from {doc.title}",
                    hook="3 things senior engineers do differently when building video factories.",
                    core_insight="Deterministic composition templates beat prompt-only rendering every single time.",
                    suggested_duration=50,
                    suggested_platform="instagram_reels",
                    source_reference=doc.title,
                ),
            ]
            return RepurposingPlan(
                source_title=doc.title,
                overall_summary=f"Analysis of {doc.title} covering operational reliability, queue safety, and deterministic rendering.",
                key_moments=moments,
                derived_shorts=shorts[:short_count],
            )

        user_prompt = f"Source Title: {doc.title}\nSource Text:\n{doc.raw_text[:4000]}\nDesired Shorts Count: {short_count}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        return validate_ai_response(raw_res, RepurposingPlan)
