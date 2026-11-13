"""API endpoints for evidence-backed channel opportunity discovery."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import Channel as DBChannel, ChannelOpportunity
from app.services.opportunity_discovery import OpportunityDiscoveryService
from app.services.search_provider import SearchProviderError

router = APIRouter()


@router.post("/{channel_id}/discover")
async def discover_channel_opportunities(
    channel_id: uuid.UUID,
    candidate_limit: int = Query(30, ge=5, le=50),
    select_count: int | None = Query(None, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    channel = await db.get(DBChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if not channel.is_active:
        raise HTTPException(status_code=409, detail="Channel is inactive")
    if not channel.nightly_enabled:
        raise HTTPException(status_code=409, detail="Nightly discovery is disabled for this channel")
    try:
        service = OpportunityDiscoveryService()
        return await service.discover(
            db=db,
            channel=channel,
            candidate_limit=candidate_limit,
            select_count=select_count,
        )
    except SearchProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Do not expose provider stack traces or prompts to API clients.
        raise HTTPException(status_code=502, detail="Opportunity assessment model failed") from exc


@router.get("/{channel_id}/opportunities")
async def list_channel_opportunities(
    channel_id: uuid.UUID,
    status: str | None = Query(None, pattern=r"^(discovered|selected|converted|rejected|archived)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    if await db.get(DBChannel, channel_id) is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    query = select(ChannelOpportunity).where(ChannelOpportunity.channel_id == channel_id)
    if status:
        query = query.where(ChannelOpportunity.status == status)
    query = query.order_by(ChannelOpportunity.score_total.desc(), ChannelOpportunity.last_seen_at.desc())
    result = await db.execute(query.offset(skip).limit(limit))
    opportunities = result.scalars().all()
    return [
        {
            "id": str(item.id),
            "channel_id": str(item.channel_id),
            "content_idea_id": str(item.content_idea_id) if item.content_idea_id else None,
            "title": item.title,
            "topic": item.normalized_topic,
            "description": item.description,
            "content_angle": item.content_angle,
            "source_evidence": item.source_evidence,
            "score_breakdown": item.score_breakdown,
            "score_total": item.score_total,
            "confidence": item.confidence,
            "rationale": item.rationale,
            "risk_flags": item.risk_flags,
            "status": item.status,
            "first_seen_at": item.first_seen_at,
            "last_seen_at": item.last_seen_at,
            "selected_at": item.selected_at,
        }
        for item in opportunities
    ]
