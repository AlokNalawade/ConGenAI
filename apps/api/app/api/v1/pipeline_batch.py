"""
Batch pipeline generation endpoints.

Creates distinct strategic angles across batch items, persists strategic DNA
in content.metadata_json, and performs an atomic single-transaction commit
of the batch, ideas, contents, and queued pipeline jobs before dispatching.
"""
import uuid
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import (
    Content as DBContent,
    ContentIdea as DBContentIdea,
    ContentBatch as DBContentBatch,
    PipelineJobDB,
)
from app.workflows.workflow_state import WorkflowState
from app.agents.batch_strategy import BatchStrategyAgent
from app.workflows.task_queue import enqueue_pipeline_job

router = APIRouter()


class BatchPipelineRequest(BaseModel):
    topic: str = Field(..., description="Topic or prompt for content batch generation")
    count: int = Field(default=3, ge=1, le=10, description="Number of content items to generate")
    platforms: List[str] = Field(default=["youtube_shorts"], description="Target platforms")
    model_overrides: Optional[Dict[str, str]] = None


@router.post("/pipeline/batch", status_code=status.HTTP_202_ACCEPTED)
@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_batch_pipeline(
    req: BatchPipelineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate multiple distinct content variations for a topic.
    Persists strategic DNA to content.metadata_json and guarantees atomicity
    by committing all records in a single database transaction before dispatching.
    """
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    platform = req.platforms[0] if req.platforms else "youtube_shorts"

    # Formulate strategic angles first (before transaction)
    batch_agent = BatchStrategyAgent()
    batch_plan = await batch_agent.generate_batch_plan(
        topic=req.topic,
        count=req.count,
        platform=platform,
    )

    # Single transaction for Batch + Ideas + Contents + PipelineJobDB records
    db_batch = DBContentBatch(
        id=batch_id,
        topic=req.topic,
        requested_count=req.count,
        status="running",
    )
    db.add(db_batch)

    job_records = []
    for variation in batch_plan.variations:
        idea = DBContentIdea(
            title=variation.title,
            topic=req.topic,
            target_audience=variation.target_audience,
            platform=platform,
            status="approved",
        )
        db.add(idea)
        await db.flush()  # get idea.id

        strategy_dna = {
            "angle": variation.angle,
            "target_audience": variation.target_audience,
            "hook_strategy": variation.hook_strategy,
            "differentiator": variation.differentiator,
            "avoid_overlap_with": variation.avoid_overlap_with,
        }

        content = DBContent(
            idea_id=idea.id,
            batch_id=batch_id,
            title=variation.title,
            platform=platform,
            status=WorkflowState.IDEA.value,
            metadata_json=strategy_dna,
        )
        db.add(content)
        await db.flush()  # get content.id

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_db = PipelineJobDB(
            id=job_id,
            content_id=content.id,
            status="queued",
            progress_percent=0,
            model_overrides=req.model_overrides or {},
            resume=False,
        )
        db.add(job_db)
        job_records.append((job_id, content.id, variation))

    # Single atomic commit for everything
    await db.commit()

    # Dispatch to Redis task queue
    queued_jobs = []
    for job_id, content_id, variation in job_records:
        await enqueue_pipeline_job(
            job_id=job_id,
            content_id=str(content_id),
            pipeline_run_id=str(uuid.uuid4()),
            model_overrides=req.model_overrides or {},
            resume=False,
        )
        queued_jobs.append({
            "job_id": job_id,
            "content_id": str(content_id),
            "title": variation.title,
            "angle": variation.angle,
            "differentiator": variation.differentiator,
        })

    return {
        "batch_id": batch_id,
        "topic": req.topic,
        "count": len(queued_jobs),
        "status": "202_accepted",
        "queued_jobs": queued_jobs,
    }
