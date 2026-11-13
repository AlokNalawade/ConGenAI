"""Morning review queue and human approval actions for generated videos."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import AgentRun, Asset, Channel, Content, Research
from app.workflows.workflow_state import (
    InvalidWorkflowTransitionError,
    WorkflowState,
    update_workflow_state,
)

router = APIRouter()


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approve|revise|reject)$")
    note: str | None = Field(default=None, max_length=2000)


@router.get("/queue")
async def review_queue(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return only fully rendered videos awaiting the explicit human gate."""
    rows = (await db.execute(
        select(Content, Channel)
        .join(Channel, Content.channel_id == Channel.id, isouter=True)
        .where(Content.status == WorkflowState.AWAITING_APPROVAL.value)
        .order_by(Content.created_at.desc())
    )).all()

    videos: list[dict[str, Any]] = []
    for content, channel in rows:
        asset_result = await db.execute(
            select(Asset)
            .where(
                Asset.content_id == content.id,
                Asset.asset_type == "video",
                Asset.status == "completed",
            )
            .order_by(Asset.created_at.desc())
        )
        video_asset = asset_result.scalars().first()
        # A status label alone is insufficient: require the actual completed render.
        if not video_asset:
            continue

        research_result = await db.execute(
            select(Research).where(Research.content_id == content.id)
        )
        research = research_result.scalars().first()
        videos.append({
            "id": str(content.id),
            "title": content.title or "Untitled video",
            "description": content.description,
            "status": content.status,
            "quality_score": content.quality_score,
            "platform": content.platform,
            "target_duration": content.target_duration,
            "created_at": content.created_at.isoformat() if content.created_at else None,
            "channel": {
                "id": str(channel.id),
                "name": channel.name,
                "niche": channel.niche,
            } if channel else None,
            "video": {
                "asset_id": str(video_asset.id),
                "path": video_asset.path,
                "mime_type": video_asset.mime_type,
                "duration": video_asset.duration,
                "provider": video_asset.provider,
                "model": video_asset.model,
            },
            "research": {
                "summary": research.summary,
                "key_points": research.key_points or [],
                "sources": research.sources or [],
                "warnings": research.warnings or [],
            } if research else None,
        })

    channel_counts: dict[str, dict[str, Any]] = {}
    for item in videos:
        channel = item["channel"] or {"id": "unassigned", "name": "Unassigned", "niche": ""}
        entry = channel_counts.setdefault(channel["id"], {
            "channel": channel, "awaiting_approval": 0,
        })
        entry["awaiting_approval"] += 1

    return {
        "count": len(videos),
        "channels": list(channel_counts.values()),
        "videos": videos,
        "approval_required": True,
        "auto_publish": False,
    }


@router.post("/{content_id}/decision")
async def decide_review(
    content_id: uuid.UUID,
    body: ReviewDecision,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Approve, send back for revision, or reject a video awaiting review."""
    result = await db.execute(select(Content).where(Content.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.status != WorkflowState.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail=f"Content is not awaiting approval (current status: {content.status})",
        )

    if body.decision == "approve":
        asset_result = await db.execute(
            select(Asset.id).where(
                Asset.content_id == content_id,
                Asset.asset_type == "video",
                Asset.status == "completed",
            ).limit(1)
        )
        if not asset_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A completed video render is required")
        target = WorkflowState.APPROVED
    elif body.decision == "revise":
        target = WorkflowState.RESEARCH
    else:
        target = WorkflowState.FAILED

    # Keep a durable audit trail of the editorial decision and optional note.
    db.add(AgentRun(
        id=uuid.uuid4(),
        content_id=content_id,
        agent="HumanReview",
        stage=f"editorial_{body.decision}",
        status="completed",
        error=body.note,
        duration_seconds=0.0,
    ))
    try:
        await update_workflow_state(db, content_id, target, force=False)
    except InvalidWorkflowTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "content_id": str(content_id),
        "decision": body.decision,
        "status": target.value,
        "note": body.note,
        "message": "Decision saved. Publishing still requires a separate approved publishing workflow."
        if body.decision == "approve" else "Review decision saved.",
    }
