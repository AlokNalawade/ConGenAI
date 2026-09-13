"""
Pipeline regeneration and stage-level rerun endpoints.

Implements concurrency guards against racing jobs (409 Conflict)
and full lineage tracking (parent_run_id, run_type, reason).
"""
import uuid
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, update

from app.db.database import get_db
from app.db.models import (
    Content as DBContent,
    PipelineRun as DBPipelineRun,
    Research as DBResearch,
    Strategy as DBStrategy,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset,
)
from app.workflows.workflow_state import WorkflowState, update_workflow_state
from app.workflows.worker import job_manager

router = APIRouter()

_STAGE_CLEAR_MAP = {
    "research": ["research", "strategy", "script", "scenes", "assets"],
    "strategy": ["strategy", "script", "scenes", "assets"],
    "script": ["script", "scenes", "assets"],
    "scenes": ["scenes", "assets"],
    "media": ["assets_media"],  # image, audio, video, subtitle
    "render": ["assets_video"],  # final video only
}

_STAGE_TO_WORKFLOW_STATE = {
    "research": WorkflowState.RESEARCH,
    "strategy": WorkflowState.STRATEGY,
    "script": WorkflowState.SCRIPT,
    "scenes": WorkflowState.SCENES,
    "media": WorkflowState.ASSETS,
    "render": WorkflowState.RENDER,
}


class RegenerateBody(BaseModel):
    mode: Literal["full", "visuals"] = Field(
        default="full",
        description=(
            "'full'    — Start a completely new pipeline run with lineage. "
            "All stages are re-run from scratch.\n"
            "'visuals' — Keep approved script and scene plan. Only regenerate "
            "images, audio, and video."
        ),
    )
    reason: Optional[str] = Field(
        default=None,
        description="Optional reason or feedback for why this regeneration was requested.",
    )


@router.post("/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_content(
    content_id: uuid.UUID,
    body: Optional[RegenerateBody] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate a content item with race condition guards and lineage tracking.
    """
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # Finding #1 Guard: Reject if an active job is already queued or running
    active_job = await job_manager.get_active_job_by_content(str(content_id))
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot regenerate content: active job '{active_job.job_id}' "
                f"is currently in status '{active_job.status}'."
            ),
        )

    mode = (body.mode if body else None) or "full"
    reason = body.reason if body else None

    # Fetch latest pipeline run for lineage tracking
    run_result = await db.execute(
        select(DBPipelineRun)
        .filter(DBPipelineRun.content_id == content_id)
        .order_by(DBPipelineRun.created_at.desc())
    )
    latest_run = run_result.scalars().first()

    if mode == "visuals":
        if not latest_run:
            raise HTTPException(
                status_code=400,
                detail="No pipeline run found for this content. Run the full pipeline first.",
            )

        run_id = latest_run.id

        # Delete only media assets for this run
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type.in_(["image", "audio", "video", "subtitle"]),
            )
        )

        # Update run status and lineage
        latest_run.status = "queued"
        latest_run.current_stage = "RESUMING_VISUALS"
        latest_run.error = None
        latest_run.run_type = "visual_regeneration"
        if reason:
            latest_run.reason = reason

        await update_workflow_state(db, content_id, WorkflowState.GENERATING_ASSETS)
        await db.commit()

        job = await job_manager.create_job(
            content_id=str(content_id),
            resume=True,
            pipeline_run_id=str(run_id),
        )

        return {
            "job_id": job.job_id,
            "content_id": str(content_id),
            "pipeline_run_id": str(run_id),
            "mode": "visuals",
            "run_type": "visual_regeneration",
            "reason": reason,
            "status": "202_accepted",
            "message": (
                "Visuals-only regeneration queued. Script and scene plan are preserved. "
                "Regenerating images, audio, and video only."
            ),
        }

    else:
        # mode == "full" -> fresh run with parent lineage
        new_run_id = uuid.uuid4()
        new_run = DBPipelineRun(
            id=new_run_id,
            content_id=content_id,
            parent_run_id=latest_run.id if latest_run else None,
            run_type="full_regeneration",
            reason=reason,
            is_current=True,
            status="queued",
            current_stage="INIT",
            model_overrides={},
        )
        db.add(new_run)

        # De-prioritize older runs
        await db.execute(
            update(DBPipelineRun)
            .where(DBPipelineRun.content_id == content_id, DBPipelineRun.id != new_run_id)
            .values(is_current=False)
        )
        await update_workflow_state(db, content_id, WorkflowState.RESEARCH)
        await db.commit()

        job = await job_manager.create_job(
            content_id=str(content_id),
            resume=False,
            pipeline_run_id=str(new_run_id),
        )

        return {
            "job_id": job.job_id,
            "content_id": str(content_id),
            "pipeline_run_id": str(new_run_id),
            "parent_run_id": str(latest_run.id) if latest_run else None,
            "mode": "full",
            "run_type": "full_regeneration",
            "reason": reason,
            "status": "202_accepted",
            "message": "Full pipeline regeneration queued with lineage tracking.",
        }


@router.post("/rerun-from/{stage}", status_code=status.HTTP_202_ACCEPTED)
async def rerun_from_stage(
    content_id: uuid.UUID,
    stage: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Re-run the pipeline from a specific stage, preserving all work done before it.
    Guarded against concurrent executions.
    """
    if stage not in _STAGE_CLEAR_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage}'. Valid values: {list(_STAGE_CLEAR_MAP.keys())}",
        )

    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # Finding #1 Guard
    active_job = await job_manager.get_active_job_by_content(str(content_id))
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot rerun stage: active job '{active_job.job_id}' "
                f"is currently in status '{active_job.status}'."
            ),
        )

    # Find latest pipeline run
    run_result = await db.execute(
        select(DBPipelineRun)
        .filter(DBPipelineRun.content_id == content_id)
        .order_by(DBPipelineRun.created_at.desc())
    )
    pipeline_run = run_result.scalars().first()
    if not pipeline_run:
        raise HTTPException(
            status_code=400,
            detail="No pipeline run found. Run the full pipeline first.",
        )
    run_id = pipeline_run.id

    what_to_clear = _STAGE_CLEAR_MAP[stage]

    if "research" in what_to_clear:
        await db.execute(
            delete(DBResearch).where(
                DBResearch.content_id == content_id,
                DBResearch.pipeline_run_id == run_id,
            )
        )
    if "strategy" in what_to_clear:
        await db.execute(
            delete(DBStrategy).where(
                DBStrategy.content_id == content_id,
                DBStrategy.pipeline_run_id == run_id,
            )
        )
    if "script" in what_to_clear:
        await db.execute(
            delete(DBScript).where(
                DBScript.content_id == content_id,
                DBScript.pipeline_run_id == run_id,
            )
        )
    if "scenes" in what_to_clear:
        await db.execute(
            delete(DBScene).where(
                DBScene.content_id == content_id,
                DBScene.pipeline_run_id == run_id,
            )
        )
    if "assets" in what_to_clear:
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
            )
        )
    elif "assets_media" in what_to_clear:
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type.in_(["image", "audio", "video", "subtitle"]),
            )
        )
    elif "assets_video" in what_to_clear:
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type == "video",
                DBAsset.scene_id.is_(None),
            )
        )

    pipeline_run.status = "queued"
    pipeline_run.current_stage = f"RERUN_FROM_{stage.upper()}"
    pipeline_run.error = None
    pipeline_run.run_type = f"stage_rerun_{stage}"
    pipeline_run.reason = f"Rerun from stage {stage}"

    target_state = _STAGE_TO_WORKFLOW_STATE[stage]
    await update_workflow_state(db, content_id, target_state, force=True)
    await db.commit()

    job = await job_manager.create_job(
        content_id=str(content_id),
        resume=True,
        pipeline_run_id=str(run_id),
    )

    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "pipeline_run_id": str(run_id),
        "rerun_from": stage,
        "status": "202_accepted",
        "message": f"Re-running pipeline from '{stage}' stage. All upstream work is preserved.",
    }
