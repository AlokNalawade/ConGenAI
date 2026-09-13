"""Content DNA Agent.

Responsible for:
1. Formulating or enriching the ContentDNA profile for a topic/brand.
2. Expanding the DNA into N distinct variations with non-overlapping angles.
"""

import os
import json
from typing import Optional
from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.content_dna import (
    ContentDNA,
    BrandArchetype,
    VoiceTone,
    VisualAesthetic,
    HookPhilosophy,
    DNAVariation,
    BatchDNAPlan,
)
from app.models.ai_contracts import validate_ai_response


class DNAAgent(BaseAgent):
    DNA_SYSTEM_PROMPT = """You are an elite Brand & Editorial Content Director.
Given a topic and context, construct a rigorous Content DNA blueprint.
Return ONLY valid JSON matching this schema:
{
    "topic": "...",
    "target_audience": "...",
    "brand_archetype": "educational_authority",
    "voice_tone": "concise_punchy",
    "visual_aesthetic": "dark_tech_cinematic",
    "hook_philosophy": "contrarian_mythbuster",
    "cta_strategy": "...",
    "core_thesis": "...",
    "negative_rules": [
        "No buzzwords like revolutionary or game changer",
        "Avoid slow intro greetings"
    ]
}"""

    EXPANSION_SYSTEM_PROMPT = """You are a Senior Content Strategist specializing in high-retention social content.
Given a Content DNA blueprint, generate N completely distinct video angles.
Each video MUST have a completely different hook and angle framework to ensure no 2 videos feel like clones.
Angles to choose from:
- Contrarian Mythbuster
- Tactical How-To / Playbook
- Failure Postmortem / Warning
- Architectural Deep-Dive
- Future Forecast / Prediction
- Case Study Breakdown

Return ONLY valid JSON with this format:
{
    "variations": [
        {
            "index": 1,
            "title": "...",
            "angle_type": "Contrarian Mythbuster",
            "hook_text": "...",
            "target_angle": "...",
            "differentiator": "...",
            "avoid_overlap_with": ["..."],
            "recommended_template": "fast_news_explainer"
        }
    ]
}"""

    async def generate_dna(
        self,
        topic: str,
        audience: Optional[str] = None,
        brand_archetype: Optional[BrandArchetype] = None,
        voice_tone: Optional[VoiceTone] = None,
        visual_aesthetic: Optional[VisualAesthetic] = None,
        hook_philosophy: Optional[HookPhilosophy] = None,
    ) -> ContentDNA:
        """Synthesize or enrich a ContentDNA profile."""
        await log_manager.broadcast(f"Synthesizing Content DNA for topic '{topic}'...", agent="DNAAgent")

        if os.getenv("TESTING") or os.getenv("DEV_MODE"):
            return ContentDNA(
                topic=topic,
                target_audience=audience or "Engineers and founders building AI systems",
                brand_archetype=brand_archetype or BrandArchetype.EDUCATIONAL_AUTHORITY,
                voice_tone=voice_tone or VoiceTone.CONCISE_PUNCHY,
                visual_aesthetic=visual_aesthetic or VisualAesthetic.DARK_TECH_CINEMATIC,
                hook_philosophy=hook_philosophy or HookPhilosophy.CONTRARIAN_MYTHBUSTER,
                cta_strategy="Follow for production-grade AI architectures",
                core_thesis=f"The reality of {topic} is defined by operational reliability, not demo hype.",
                negative_rules=[
                    "No superficial marketing buzzwords",
                    "Never start with 'Hey everyone'",
                    "Stick to verified facts and clear technical trade-offs",
                ],
            )

        user_prompt = f"Topic: {topic}\nTarget Audience: {audience or 'Tech Professionals'}"
        raw_res = await self.run(self.DNA_SYSTEM_PROMPT, user_prompt, json_mode=True)
        return validate_ai_response(raw_res, ContentDNA)

    async def expand_dna_batch(
        self,
        dna: ContentDNA,
        count: int = 3,
    ) -> BatchDNAPlan:
        """Expand 1 ContentDNA profile into N distinct batch variations."""
        await log_manager.broadcast(f"Expanding DNA for '{dna.topic}' into {count} diverse batch variations...", agent="DNAAgent")

        if os.getenv("TESTING") or os.getenv("DEV_MODE"):
            frameworks = [
                ("Contrarian Mythbuster", f"Why 90% of {dna.topic} projects fail in production", "Focuses on common misconceptions and deployment pitfalls"),
                ("Tactical Playbook", f"The 3-step architecture for resilient {dna.topic}", "Step-by-step implementation blueprint with code/diagram patterns"),
                ("Failure Postmortem", f"We broke our {dna.topic} pipeline so you don't have to", "Real-world debugging war story with actionable takeaways"),
                ("Future Forecast", f"What {dna.topic} will look like by 2027", "Emerging paradigms, architectural shifts, and upcoming standards"),
                ("Speed Teardown", f"Zero to production with {dna.topic} in 60 seconds", "Fast-paced high-signal walkthrough of core capabilities"),
            ]
            variations = []
            for i in range(count):
                idx = i % len(frameworks)
                angle_type, title, diff = frameworks[idx]
                avoid = [frameworks[j][1] for j in range(count) if j != i]
                variations.append(
                    DNAVariation(
                        index=i + 1,
                        title=f"{title} (Part {i+1})" if i >= len(frameworks) else title,
                        angle_type=angle_type,
                        hook_text=f"Stop doing {dna.topic} wrong. Here is what actually happens:" if i == 0 else f"Most engineers miss this critical part of {dna.topic}:",
                        target_angle=f"Angle focusing on {angle_type.lower()}",
                        differentiator=diff,
                        avoid_overlap_with=avoid,
                        recommended_template="fast_news_explainer" if i % 2 == 0 else "hormozi_bold",
                    )
                )
            return BatchDNAPlan(dna=dna, variations=variations, total_count=len(variations))

        user_prompt = f"Content DNA:\n{dna.model_dump_json(indent=2)}\nRequested Variation Count: {count}"
        raw_res = await self.run(self.EXPANSION_SYSTEM_PROMPT, user_prompt, json_mode=True)
        data = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
        raw_variations = data.get("variations", [])
        variations = [validate_ai_response(v, DNAVariation) for v in raw_variations]
        return BatchDNAPlan(dna=dna, variations=variations, total_count=len(variations))
