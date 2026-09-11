from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, Dict, List
import uuid

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import (
    Content as DBContent,
    ContentIdea as DBContentIdea,
    ContentBatch as DBContentBatch,
    Research as DBResearch,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset
)
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_state import WorkflowState, update_workflow_state
from app.workflows.worker import job_manager

router = APIRouter()


class PipelineRequest(BaseModel):
    content_id: uuid.UUID
    model_overrides: Optional[Dict[str, str]] = None
    resume: bool = True
    idempotency_key: Optional[str] = None


class BatchPipelineRequest(BaseModel):
    topic: str = Field(..., description="Topic or prompt for content batch generation")
    count: int = Field(default=3, ge=1, le=10, description="Number of content items to generate")
    platforms: List[str] = Field(default=["youtube_shorts"], description="Target platforms")
    model_overrides: Optional[Dict[str, str]] = None


@router.post("/pipeline", status_code=status.HTTP_202_ACCEPTED)
async def trigger_content_pipeline(
    content_id: uuid.UUID,
    model_overrides: Optional[Dict[str, str]] = None,
    resume: bool = True,
    idempotency_key: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = await job_manager.create_job(
        content_id=str(content_id),
        model_overrides=model_overrides,
        resume=resume,
        idempotency_key=idempotency_key
    )

    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "202_accepted",
        "message": f"Pipeline job '{job.job_id}' queued for processing via Redis worker."
    }


@router.post("/pipeline/batch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_batch_pipeline(
    req: BatchPipelineRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.agents.batch_strategy import BatchStrategyAgent

    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    platform = req.platforms[0] if req.platforms else "youtube_shorts"

    # Formulate strategic angles first (before transaction)
    batch_agent = BatchStrategyAgent()
    batch_plan = await batch_agent.generate_batch_plan(topic=req.topic, count=req.count, platform=platform)

    # Issue #7: Single transaction for all Idea + Content creation
    db_batch = DBContentBatch(
        id=batch_id,
        topic=req.topic,
        requested_count=req.count,
        status="running"
    )
    db.add(db_batch)

    items = []
    for variation in batch_plan.variations:
        idea = DBContentIdea(
            title=variation.title,
            topic=req.topic,
            target_audience=variation.target_audience,
            platform=platform,
            status="approved"
        )
        db.add(idea)
        await db.flush()  # get idea.id without committing

        content = DBContent(
            idea_id=idea.id,
            batch_id=batch_id,
            title=variation.title,
            platform=platform,
            status=WorkflowState.IDEA.value
        )
        db.add(content)
        await db.flush()  # get content.id without committing
        items.append((content, variation))

    # Single commit for all batch items
    await db.commit()

    # Enqueue jobs outside the transaction
    queued_jobs = []
    for content, variation in items:
        job = await job_manager.create_job(
            content_id=str(content.id),
            model_overrides=req.model_overrides,
            resume=False
        )
        queued_jobs.append({
            "job_id": job.job_id,
            "content_id": str(content.id),
            "title": variation.title,
            "angle": variation.angle
        })

    return {
        "batch_id": batch_id,
        "topic": req.topic,
        "count": len(queued_jobs),
        "status": "202_accepted",
        "queued_jobs": queued_jobs
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/resume")
async def resume_content_pipeline(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = await job_manager.create_job(content_id=str(content_id), resume=True)
    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "resumed",
        "message": f"Resuming pipeline for content {content_id} from last valid stage."
    }


@router.get("/pipeline")
async def get_pipeline_status(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    research_res = await db.execute(select(DBResearch).filter(DBResearch.content_id == content_id))
    research = research_res.scalars().first()

    script_res = await db.execute(select(DBScript).filter(DBScript.content_id == content_id).order_by(DBScript.created_at.desc()))
    script = script_res.scalars().first()

    scenes_res = await db.execute(select(DBScene).filter(DBScene.content_id == content_id))
    scenes = scenes_res.scalars().all()

    video_res = await db.execute(select(DBAsset).filter(DBAsset.content_id == content_id, DBAsset.asset_type == "video").order_by(DBAsset.created_at.desc()))
    video_asset = video_res.scalars().first()

    active_job = await job_manager.get_job_by_content(str(content_id))

    return {
        "content_id": str(content_id),
        "title": content.title,
        "status": content.status,
        "quality_score": content.quality_score,
        "has_research": research is not None,
        "has_script": script is not None,
        "scene_count": len(scenes),
        "video_asset_path": video_asset.path if video_asset else None,
        "is_approved": content.status == WorkflowState.APPROVED.value,
        "is_published": content.status == WorkflowState.PUBLISHED.value,
        "active_job": active_job.to_dict() if active_job else None
    }


@router.post("/approve")
async def approve_content(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    await update_workflow_state(db, content_id, WorkflowState.APPROVED, force=True)
    return {
        "content_id": str(content_id),
        "status": WorkflowState.APPROVED.value,
        "message": "Content successfully approved for publishing!"
    }


@router.post("/regenerate")
async def regenerate_content(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = await job_manager.create_job(content_id=str(content_id), resume=False)
    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "202_accepted",
        "message": "Pipeline regeneration triggered."
    }
