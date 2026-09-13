"""
Pipeline orchestration router.

Coordinates content generation jobs, status inquiries, and mounts modular subrouters:
- pipeline_batch: Batch generation with distinct angles and atomic persistence
- pipeline_regeneration: Full and visuals regeneration with concurrency guards and lineage
- pipeline_inspector: Deep stage inspection powered by PipelineSnapshotService
- approvals: Strict approval validation and audited administrative overrides
"""
import uuid
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_db
from app.db.models import Content as DBContent
from app.workflows.worker import job_manager
from app.services.pipeline_snapshot_service import PipelineSnapshotService

# Modular sub-routers
from app.api.v1 import approvals
from app.api.v1 import pipeline_batch
from app.api.v1 import pipeline_regeneration
from app.api.v1 import pipeline_inspector

router = APIRouter()

# Include modular subrouters
router.include_router(approvals.router)
router.include_router(pipeline_batch.router)
router.include_router(pipeline_regeneration.router)
router.include_router(pipeline_inspector.router)


class PipelineRequest(BaseModel):
    content_id: uuid.UUID
    model_overrides: Optional[Dict[str, str]] = None
    resume: bool = True
    idempotency_key: Optional[str] = None


class PipelineTriggerBody(BaseModel):
    model_overrides: Optional[Dict[str, str]] = None
    resume: bool = True
    idempotency_key: Optional[str] = None


@router.post("/pipeline", status_code=status.HTTP_202_ACCEPTED)
async def trigger_content_pipeline(
    content_id: uuid.UUID,
    body: Optional[PipelineTriggerBody] = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a pipeline job for a content item."""
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    model_overrides = body.model_overrides if body else None
    resume = body.resume if body else True
    idempotency_key = body.idempotency_key if body else None

    job = await job_manager.create_job(
        content_id=str(content_id),
        model_overrides=model_overrides,
        resume=resume,
        idempotency_key=idempotency_key,
    )

    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "202_accepted",
        "message": f"Pipeline job '{job.job_id}' queued for processing.",
    }


@router.get("/pipeline")
async def get_pipeline_status(
    content_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Return concise, canonical-run aware pipeline status.
    Uses PipelineSnapshotService to stay perfectly consistent with /inspect.
    """
    summary = await PipelineSnapshotService.get_summary_status(db, content_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Content not found")
    return summary


@router.post("/resume")
async def resume_content_pipeline(
    content_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Resume execution for an existing content pipeline."""
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = await job_manager.create_job(content_id=str(content_id), resume=True)
    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "resumed",
        "message": f"Resuming pipeline for content {content_id} from last valid stage.",
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Retrieve job execution status and progress."""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()
