"""Platform Adapter Agent.

Adapts a master piece of content into platform-native variants:
- YouTube Longform (detailed chaptered narrative)
- YouTube Shorts (high-retention loopable short)
- Instagram Reels (visually engaging, shareable caption)
- TikTok (conversational, raw energy, controversial question)
- LinkedIn (structured corporate thought leadership + carousel)
- X / Twitter (hook tweet + 5-7 tweet thread + teaser)
"""

import os
from typing import List, Optional, Dict, Any
from app.agents.base import BaseAgent
from app.core.logging import log_manager
from app.models.platforms import (
    SocialPlatform,
    PlatformSpec,
    PLATFORM_SPECS,
    PlatformAdaptedContent,
)
from app.models.ai_contracts import validate_ai_response


class PlatformAdapterAgent(BaseAgent):
    SYSTEM_PROMPT = """You are a World-Class Social Media Growth Strategist & Platform Adaptation Specialist.
Given a master piece of content and a target platform, adapt the material into a platform-native format.
Do NOT just copy-paste or resize the text.
Each platform requires its own distinct:
- Hook style (e.g. curiosity gap for Shorts, professional vulnerability for LinkedIn, bold claim for TikTok)
- Duration and pacing
- Caption style and formatting
- Hashtags (platform-specific quantity)
- Call to Action (CTA)

Return ONLY valid JSON with this format:
{
    "platform": "youtube_shorts",
    "title": "...",
    "hook": "...",
    "script": "...",
    "target_duration": 45,
    "aspect_ratio": "9:16",
    "caption": "...",
    "hashtags": ["#ai", "#agents", "#tech"],
    "cta": "...",
    "thread_tweets": ["Tweet 1", "Tweet 2..."],
    "carousel_slides": ["Slide 1: Title", "Slide 2: Context..."]
}"""

    async def adapt_content(
        self,
        master_title: str,
        master_topic: str,
        core_narrative: str,
        target_platform: SocialPlatform,
        key_points: Optional[List[str]] = None,
    ) -> PlatformAdaptedContent:
        """Adapt a master narrative for a specific social platform."""
        spec: PlatformSpec = PLATFORM_SPECS.get(target_platform, PLATFORM_SPECS[SocialPlatform.YOUTUBE_SHORTS])
        await log_manager.broadcast(
            f"Adapting '{master_title}' for platform '{spec.display_name}' ({spec.aspect_ratio}, {spec.target_duration_seconds}s)...",
            agent="PlatformAdapterAgent",
        )

        if os.getenv("TESTING") or os.getenv("DEV_MODE"):
            # Deterministic platform-native mocks
            if target_platform == SocialPlatform.LINKEDIN:
                return PlatformAdaptedContent(
                    platform=target_platform,
                    title=f"The Strategic Reality of {master_topic}",
                    hook=f"Most teams building {master_topic} are optimizing for the wrong metric.",
                    script=f"In production, {master_topic} comes down to 3 things: reliability, cost, and developer experience.\n\nHere is what we learned after running millions of requests.",
                    target_duration=spec.target_duration_seconds,
                    aspect_ratio=spec.aspect_ratio,
                    caption=f"Here is why {master_topic} fails in enterprise environments:\n\n1. Latency spikes\n2. Lack of deterministic workflows\n3. Weak observability\n\nWhat is your team's biggest hurdle?",
                    hashtags=["#SoftwareEngineering", "#EnterpriseAI", "#TechLeadership"],
                    cta="Share your thoughts below in the comments.",
                    carousel_slides=[
                        f"Slide 1: The Truth About {master_topic}",
                        "Slide 2: Why Prototypes Lie",
                        "Slide 3: The 3 Core Bottlenecks",
                        "Slide 4: Production Architecture",
                        "Slide 5: Key Takeaways",
                    ],
                )
            elif target_platform == SocialPlatform.X_THREAD:
                return PlatformAdaptedContent(
                    platform=target_platform,
                    title=f"{master_topic} Deep Dive Thread",
                    hook=f"Everyone is talking about {master_topic}, but 95% of people are misunderstanding how it works.",
                    script=f"A 40-second breakdown of the core mechanics behind {master_topic}.",
                    target_duration=spec.target_duration_seconds,
                    aspect_ratio=spec.aspect_ratio,
                    caption=f"A masterclass on {master_topic} in 6 tweets. 🧵👇",
                    hashtags=["#buildinpublic"],
                    cta="Retweet the first tweet if you found this useful!",
                    thread_tweets=[
                        f"1/6: Everyone is talking about {master_topic}, but 95% of teams get stuck in demo land.",
                        f"2/6: The biggest bottleneck isn't the model. It's the queue orchestration and deterministic fallback state.",
                        f"3/6: Here is the architectural layout we use to maintain 99.9% uptime.",
                        f"4/6: Notice how the data models separate raw assets from pipeline executions.",
                        f"5/6: If you're building in this space, avoid these 3 mistakes.",
                        f"6/6: That's a wrap! Follow @congenai for more daily architecture breakdowns.",
                    ],
                )
            elif target_platform == SocialPlatform.TIKTOK:
                return PlatformAdaptedContent(
                    platform=target_platform,
                    title=f"Stop Doing {master_topic} Wrong",
                    hook=f"Stop scrolling if you're trying to build {master_topic} right now.",
                    script=f"Everyone thinks {master_topic} is easy until they deploy it. Here is the one bug that took down our entire worker cluster.",
                    target_duration=spec.target_duration_seconds,
                    aspect_ratio=spec.aspect_ratio,
                    caption=f"Have you run into this bug yet? Let me know below! 👇",
                    hashtags=["#techtok", "#coding", "#softwareengineer", "#ai"],
                    cta="Drop your hot take in the comments.",
                )
            else:
                # Default YouTube Shorts / Reels
                return PlatformAdaptedContent(
                    platform=target_platform,
                    title=f"The Untold Truth About {master_topic}",
                    hook=f"Here is why nobody is telling you the truth about {master_topic}.",
                    script=f"{core_narrative[:200]}...",
                    target_duration=spec.target_duration_seconds,
                    aspect_ratio=spec.aspect_ratio,
                    caption=f"The full breakdown of {master_topic}. Subscribe for more daily breakdowns! #shorts #tech",
                    hashtags=["#shorts", "#tech", "#software"],
                    cta="Subscribe for daily architectural breakdowns.",
                )

        user_prompt = f"Topic: {master_topic}\nTitle: {master_title}\nNarrative: {core_narrative}\nTarget Platform: {target_platform.value}\nPlatform Specs: {spec.model_dump_json()}"
        raw_res = await self.run(self.SYSTEM_PROMPT, user_prompt, json_mode=True)
        return validate_ai_response(raw_res, PlatformAdaptedContent)

    async def adapt_to_all_platforms(
        self,
        master_title: str,
        master_topic: str,
        core_narrative: str,
        platforms: Optional[List[SocialPlatform]] = None,
    ) -> Dict[SocialPlatform, PlatformAdaptedContent]:
        """Generate a complete multi-platform campaign from 1 master story."""
        target_platforms = platforms or [
            SocialPlatform.YOUTUBE_SHORTS,
            SocialPlatform.INSTAGRAM_REELS,
            SocialPlatform.TIKTOK,
            SocialPlatform.LINKEDIN,
            SocialPlatform.X_THREAD,
        ]
        results = {}
        for p in target_platforms:
            results[p] = await self.adapt_content(
                master_title=master_title,
                master_topic=master_topic,
                core_narrative=core_narrative,
                target_platform=p,
            )
        return results
