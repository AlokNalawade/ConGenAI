"""Morning review queue and human approval actions for generated videos."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import (
    Asset, Channel, Content, PipelineJobDB, PipelineRun, Research, ReviewAudit,
)
from app.workflows.worker import job_manager
from app.workflows.workflow_state import WorkflowState

router = APIRouter()


class ReviewDecision(BaseModel):
    decision: str = Field(pattern="^(approve|revise|reject)$")
    note: str | None = Field(default=None, max_length=2000)


@router.get("/queue")
async def review_queue(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return rendered videos awaiting the explicit human approval gate."""
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
                Asset.path.is_not(None),
                Asset.path != "",
            )
            .order_by(Asset.created_at.desc())
        )
        video_asset = asset_result.scalars().first()
        if not video_asset:
            continue

        # Prefer research tied to the current pipeline run. Only use legacy
        # unassociated research when no current run-specific record exists.
        current_run_result = await db.execute(
            select(PipelineRun)
            .where(PipelineRun.content_id == content.id, PipelineRun.is_current == 1)
            .order_by(PipelineRun.created_at.desc())
            .limit(1)
        )
        current_run = current_run_result.scalars().first()
        research_query = select(Research).where(Research.content_id == content.id)
        if current_run:
            research_query = research_query.where(
                Research.pipeline_run_id == current_run.id
            )
        else:
            research_query = research_query.where(Research.pipeline_run_id.is_(None))
        research_result = await db.execute(
            research_query.order_by(Research.created_at.desc()).limit(1)
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
            "pipeline_run_id": str(current_run.id) if current_run else None,
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


@router.post("/{content_id}/decision", status_code=status.HTTP_200_OK)
async def decide_review(
    content_id: uuid.UUID,
    body: ReviewDecision,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Persist one serialized editorial decision; revision requests enqueue a new run."""
    result = await db.execute(
        select(Content).where(Content.id == content_id).with_for_update()
    )
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    if content.status != WorkflowState.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail=f"Content is not awaiting approval (current status: {content.status})",
        )

    previous_state = content.status
    current_run_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.content_id == content_id, PipelineRun.is_current == 1)
        .order_by(PipelineRun.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    current_run = current_run_result.scalars().first()

    if body.decision == "approve":
        asset_result = await db.execute(
            select(Asset.id).where(
                Asset.content_id == content_id,
                Asset.asset_type == "video",
                Asset.status == "completed",
                Asset.path.is_not(None),
                Asset.path != "",
            ).limit(1)
        )
        if not asset_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A completed video render is required")
        target = WorkflowState.APPROVED
    elif body.decision == "revise":
        active_result = await db.execute(
            select(PipelineJobDB.id).where(
                PipelineJobDB.content_id == content_id,
                PipelineJobDB.status.in_(["queued", "dispatching", "running", "resuming"]),
            ).limit(1)
        )
        if active_result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="A pipeline job is already active for this content")
        target = WorkflowState.RESEARCH
    else:
        target = WorkflowState.FAILED

    revision_run_id = None
    if body.decision == "revise":
        revision_run_id = uuid.uuid4()
        if current_run:
            current_run.is_current = 0
        db.add(PipelineRun(
            id=revision_run_id,
            content_id=content_id,
            parent_run_id=current_run.id if current_run else None,
            is_current=1,
            run_type="review_revision",
            reason=body.note,
            status="queued",
            current_stage="INIT",
            model_overrides={},
        ))

    content.status = target.value
    db.add(ReviewAudit(
        id=uuid.uuid4(),
        content_id=content_id,
        pipeline_run_id=revision_run_id or (current_run.id if current_run else None),
        decision=body.decision,
        note=body.note,
        previous_state=previous_state,
        new_state=target.value,
    ))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    if body.decision == "revise":
        try:
            job = await job_manager.create_job(
                content_id=str(content_id),
                resume=False,
                pipeline_run_id=str(revision_run_id),
                idempotency_key=f"review-revision:{content_id}:{revision_run_id}",
            )
        except Exception as exc:
            # The editorial decision and run are durable. Surface the enqueue
            # problem explicitly rather than reporting a successful dispatch.
            raise HTTPException(
                status_code=503,
                detail=(
                    "Revision decision was saved, but the pipeline job could not be "
                    f"dispatched. The queued run is preserved for recovery: {exc}"
                ),
            ) from exc
        return {
            "content_id": str(content_id),
            "decision": body.decision,
            "status": target.value,
            "pipeline_run_id": str(revision_run_id),
            "job_id": job.job_id,
            "job_status": job.status,
            "note": body.note,
            "message": "Revision queued. Publishing remains disabled and requires a separate approval.",
        }

    return {
        "content_id": str(content_id),
        "decision": body.decision,
        "status": target.value,
        "pipeline_run_id": str(current_run.id) if current_run else None,
        "note": body.note,
        "message": (
            "Approved only. This action does not publish; publishing remains a separate step."
            if body.decision == "approve" else "Video rejected. No publishing action was performed."
        ),
    }
