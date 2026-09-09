from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Optional, Dict, Any
import uuid

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import Content as DBContent, Research as DBResearch, Script as DBScript, Scene as DBScene, Asset as DBAsset
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_state import WorkflowState, update_workflow_state
from app.workflows.worker import job_manager

router = APIRouter()

@router.post("/pipeline", status_code=status.HTTP_202_ACCEPTED)
async def trigger_content_pipeline(
    content_id: uuid.UUID,
    model_overrides: Optional[Dict[str, str]] = None,
    sync: bool = False,
    resume: bool = True,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = job_manager.create_job(str(content_id))

    if sync:
        await job_manager.run_job(job.job_id, sync=True)
        return {
            "job_id": job.job_id,
            "content_id": str(content_id),
            "status": job.status,
            "current_stage": job.current_stage,
            "error": job.error
        }
    else:
        await job_manager.run_job(job.job_id, sync=False)
        return {
            "job_id": job.job_id,
            "content_id": str(content_id),
            "status": "202_accepted",
            "message": f"Autonomous pipeline job '{job.job_id}' queued and processing."
        }

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@router.post("/resume")
async def resume_content_pipeline(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = job_manager.create_job(str(content_id))
    await job_manager.run_job(job.job_id, sync=False)
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

    active_job = job_manager.get_job_by_content(str(content_id))

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

    await update_workflow_state(db, content_id, WorkflowState.APPROVED)
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

    job = job_manager.create_job(str(content_id))
    await job_manager.run_job(job.job_id, sync=False)
    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "202_accepted",
        "message": "Pipeline regeneration triggered."
    }
