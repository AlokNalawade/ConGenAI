"""Channel-scoped research, scoring and selection of content opportunities."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.opportunity import OpportunityDiscoveryAgent
from app.core.config import settings
from app.db.models import (
    Channel,
    ChannelOpportunity,
    ChannelTopicHistory,
    ContentIdea,
)
from app.services.search_provider import WebSearchProvider


WEIGHTS = {
    "audience_demand": 0.25,
    "monetization_fit": 0.25,
    "competition_gap": 0.15,
    "retention_potential": 0.15,
    "originality": 0.10,
    "production_feasibility": 0.10,
}


def normalize_topic(value: str) -> str:
    value = re.sub(r"[^\w\s-]", " ", (value or "").casefold())
    return " ".join(value.split())[:300]


def calculate_opportunity_score(scores: dict[str, float]) -> float:
    """Deterministic weighted score; individual dimensions remain visible."""
    return round(sum(float(scores.get(key, 0)) * weight for key, weight in WEIGHTS.items()), 2)


def build_search_queries(channel: Channel, year: int | None = None) -> list[str]:
    year = year or datetime.now(timezone.utc).year
    niche = channel.niche.strip()
    audience = (channel.target_audience or "").strip()
    boundaries = [str(x).strip() for x in (channel.topic_boundaries or []) if str(x).strip()]
    focus = " ".join(boundaries[:2])
    audience_phrase = f" for {audience}" if audience else ""
    queries = [
        f"{niche} latest developments {year}",
        f"{niche} surprising facts explained{audience_phrase}",
        f"{niche} case studies discoveries controversies",
        f"{niche} trends statistics misconceptions",
        f"{niche} untold stories deep dive",
    ]
    if focus:
        queries.append(f"{niche} {focus}")
    strategy = channel.monetization_strategy or {}
    keywords = strategy.get("research_keywords", [])
    if isinstance(keywords, list):
        for keyword in keywords[:2]:
            if str(keyword).strip():
                queries.append(f"{niche} {str(keyword).strip()}")
    # Preserve order while avoiding duplicate provider calls.
    return list(dict.fromkeys(q.strip() for q in queries if q.strip()))[:7]


def configured_source_domains(channel: Channel) -> list[str]:
    """Read optional source restrictions from a channel's research_sources profile."""
    domains: list[str] = []
    for source in (channel.research_sources or []):
        if not isinstance(source, dict) or source.get("enabled", True) is False:
            continue
        candidate = source.get("domain") or source.get("url")
        if not candidate:
            continue
        raw = str(candidate).strip()
        if "://" not in raw:
            if "/" in raw or ":" in raw or " " in raw:
                continue
            raw = f"https://{raw}"
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            continue
        host = (parsed.hostname or "").lower()
        if host and host not in domains:
            domains.append(host)
    return domains[:10]


def _source_allowed(candidate: dict[str, Any]) -> bool:
    parsed = urlparse(str(candidate.get("url") or ""))
    return parsed.scheme in ("http", "https") and bool(parsed.netloc) and bool(candidate.get("title"))


def _contains_excluded_topic(candidate: dict[str, Any], excluded: list[str]) -> bool:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')}".casefold()
    return any(term.casefold() in text for term in excluded if term and len(term.strip()) >= 3)


class OpportunityDiscoveryService:
    def __init__(self, search_provider: WebSearchProvider | None = None, agent=None):
        self.search_provider = search_provider or WebSearchProvider()
        self.agent = agent or OpportunityDiscoveryAgent()

    async def discover(
        self,
        db: AsyncSession,
        channel: Channel,
        candidate_limit: int = 30,
        select_count: int | None = None,
    ) -> dict[str, Any]:
        if not channel.is_active:
            raise ValueError("Channel is inactive")
        if not channel.nightly_enabled:
            raise ValueError("Nightly discovery is disabled for this channel")

        target = select_count if select_count is not None else channel.nightly_video_target
        if target < 1 or target > 20:
            raise ValueError("select_count must be between 1 and 20")
        candidate_limit = max(5, min(candidate_limit, 50))

        raw_results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        queries = build_search_queries(channel)
        source_domains = configured_source_domains(channel)
        per_query = max(5, min(12, (candidate_limit + len(queries) - 1) // len(queries)))
        for query in queries:
            results = await self.search_provider.search(query, limit=per_query, domains=source_domains or None)
            for item in results:
                if not _source_allowed(item):
                    continue
                url_key = item["url"].rstrip("/").casefold()
                if url_key in seen_urls or _contains_excluded_topic(item, channel.excluded_topics or []):
                    continue
                seen_urls.add(url_key)
                raw_results.append(item)
                if len(raw_results) >= candidate_limit:
                    break
            if len(raw_results) >= candidate_limit:
                break

        if not raw_results:
            return {
                "channel_id": str(channel.id),
                "queries": queries,
                "discovered_count": 0,
                "selected_count": 0,
                "requested_count": target,
                "shortfall": target,
                "opportunities": [],
                "message": "The search provider returned no usable source results.",
            }

        channel_data = {
            "name": channel.name,
            "niche": channel.niche,
            "description": channel.description,
            "target_audience": channel.target_audience,
            "language": channel.language,
            "platforms": channel.platforms,
            "topic_boundaries": channel.topic_boundaries,
            "excluded_topics": channel.excluded_topics,
            "monetization_strategy": channel.monetization_strategy,
            "content_format": channel.content_format,
        }
        valid_assessments = []
        # Chunk the candidates so local models are not asked to score a huge prompt.
        for offset in range(0, len(raw_results), 8):
            chunk = raw_results[offset:offset + 8]
            indexed = [
                {"source_index": offset + index, **item}
                for index, item in enumerate(chunk)
            ]
            batch = await self.agent.assess(channel_data, indexed)
            # Reject hallucinated or cross-chunk indices instead of attaching an
            # assessment to a source that was not included in that model request.
            for assessment in batch.assessments:
                if not offset <= assessment.source_index < offset + len(chunk):
                    continue
                if assessment.niche_fit < 60:
                    continue
                valid_assessments.append(assessment)

        history_result = await db.execute(
            select(ChannelTopicHistory.normalized_topic, ChannelTopicHistory.topic).where(
                ChannelTopicHistory.channel_id == channel.id
            )
        )
        # Re-normalize the display topic too, because the phase-one migration
        # backfill used a simpler lower/trim transform for legacy records.
        used_topics = set()
        for stored_normalized, stored_topic in history_result.all():
            used_topics.add(normalize_topic(stored_normalized or ""))
            used_topics.add(normalize_topic(stored_topic or ""))

        scored = []
        seen_scored_topics = set()
        for assessment in valid_assessments:
            normalized = normalize_topic(assessment.topic or assessment.title)
            if not normalized or normalized in used_topics or normalized in seen_scored_topics:
                continue
            seen_scored_topics.add(normalized)
            score_parts = {
                key: getattr(assessment, key)
                for key in WEIGHTS
            }
            total = calculate_opportunity_score(score_parts)
            if total < settings.DISCOVERY_MIN_SCORE:
                continue
            source = raw_results[assessment.source_index]
            scored.append({
                "assessment": assessment,
                "normalized_topic": normalized,
                "score_parts": score_parts,
                "score_total": total,
                "source": source,
            })

        scored.sort(
            key=lambda item: (
                item["score_total"],
                item["assessment"].confidence,
                item["assessment"].audience_demand,
            ),
            reverse=True,
        )

        # Persist every scored opportunity, not only the selected ideas.
        persisted = []
        for item in scored:
            assessment = item["assessment"]
            existing_result = await db.execute(
                select(ChannelOpportunity).where(
                    ChannelOpportunity.channel_id == channel.id,
                    ChannelOpportunity.normalized_topic == item["normalized_topic"],
                )
            )
            opportunity = existing_result.scalar_one_or_none()
            evidence = [{
                "title": item["source"]["title"],
                "url": item["source"]["url"],
                "snippet": item["source"].get("snippet", ""),
                "published_at": item["source"].get("published_at"),
                "provider": item["source"].get("provider"),
                "query": item["source"].get("query"),
            }]
            if opportunity is None:
                opportunity = ChannelOpportunity(
                    channel_id=channel.id,
                    title=assessment.title,
                    normalized_topic=item["normalized_topic"],
                    description=assessment.description,
                    content_angle=assessment.content_angle,
                    source_evidence=evidence,
                    score_breakdown=item["score_parts"],
                    score_total=item["score_total"],
                    confidence=assessment.confidence,
                    rationale=assessment.rationale,
                    risk_flags=assessment.risk_flags,
                    status="discovered",
                )
                db.add(opportunity)
            else:
                opportunity.title = assessment.title
                opportunity.description = assessment.description
                opportunity.content_angle = assessment.content_angle
                opportunity.source_evidence = evidence
                opportunity.score_breakdown = item["score_parts"]
                opportunity.score_total = item["score_total"]
                opportunity.confidence = assessment.confidence
                opportunity.rationale = assessment.rationale
                opportunity.risk_flags = assessment.risk_flags
                opportunity.last_seen_at = datetime.now(timezone.utc)
                if opportunity.status not in ("selected", "converted", "rejected", "archived"):
                    opportunity.status = "discovered"
            persisted.append((opportunity, item))

        await db.flush()
        selected = []
        platform = (channel.platforms or ["YouTube Shorts"])[0]
        for opportunity, item in persisted:
            if len(selected) >= target:
                break
            if opportunity.status in ("selected", "converted", "rejected", "archived"):
                continue
            assessment = item["assessment"]
            idea = ContentIdea(
                channel_id=channel.id,
                title=assessment.title,
                description=assessment.description,
                topic=assessment.topic or assessment.title,
                niche=channel.niche,
                target_audience=channel.target_audience or "General",
                platform=platform,
                content_type=channel.content_format,
                priority=int(round(item["score_total"])),
                status="discovered",
                source=item["source"]["url"],
            )
            db.add(idea)
            await db.flush()
            db.add(ChannelTopicHistory(
                channel_id=channel.id,
                normalized_topic=item["normalized_topic"],
                topic=assessment.topic or assessment.title,
                content_idea_id=idea.id,
            ))
            opportunity.content_idea_id = idea.id
            opportunity.status = "selected"
            opportunity.selected_at = datetime.now(timezone.utc)
            selected.append({
                "opportunity_id": str(opportunity.id),
                "idea_id": str(idea.id),
                "title": idea.title,
                "score": item["score_total"],
                "score_breakdown": item["score_parts"],
                "confidence": assessment.confidence,
                "content_angle": assessment.content_angle,
                "source_url": item["source"]["url"],
                "risk_flags": assessment.risk_flags,
            })

        await db.commit()
        return {
            "channel_id": str(channel.id),
            "channel_name": channel.name,
            "queries": queries,
            "sources_reviewed": len(raw_results),
            "discovered_count": len(scored),
            "selected_count": len(selected),
            "requested_count": target,
            "shortfall": max(0, target - len(selected)),
            "opportunities": selected,
            "message": (
                "Target met." if len(selected) >= target
                else "Insufficient qualifying opportunities; no unsupported topics were added."
            ),
        }
