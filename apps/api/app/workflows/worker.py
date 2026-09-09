import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from app.db.database import AsyncSessionLocal
from app.workflows.content_pipeline import ContentPipeline
from app.core.logging import log_manager

logger = logging.getLogger(__name__)

class PipelineJob:
    def __init__(self, job_id: str, content_id: str):
        self.job_id = job_id
        self.content_id = content_id
        self.status = "queued"  # queued, running, completed, failed
        self.current_stage = "NEW"
        self.progress_percent = 0
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "content_id": self.content_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress_percent": self.progress_percent,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error
        }

class JobManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance.jobs: Dict[str, PipelineJob] = {}
        return cls._instance

    def create_job(self, content_id: str) -> PipelineJob:
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = PipelineJob(job_id, content_id)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[PipelineJob]:
        return self.jobs.get(job_id)

    def get_job_by_content(self, content_id: str) -> Optional[PipelineJob]:
        for j in self.jobs.values():
            if j.content_id == str(content_id):
                return j
        return None

    async def run_job(self, job_id: str, sync: bool = False):
        job = self.jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        
        await log_manager.broadcast(
            f"🚀 [JobWorker] Started pipeline execution for job {job_id} (content: {job.content_id})",
            agent="JobWorker"
        )

        async def _execute():
            async with AsyncSessionLocal() as db:
                pipeline = ContentPipeline(db)
                try:
                    context = await pipeline.run(uuid.UUID(job.content_id))
                    job.status = "completed"
                    job.current_stage = context.current_state.value
                    job.progress_percent = 100
                    job.completed_at = datetime.utcnow()
                    await log_manager.broadcast(
                        f"✅ [JobWorker] Pipeline execution completed for content {job.content_id}",
                        agent="JobWorker"
                    )
                except Exception as e:
                    job.status = "failed"
                    job.error = str(e)
                    job.completed_at = datetime.utcnow()
                    logger.error(f"Job {job_id} failed: {e}", exc_info=True)
                    await log_manager.broadcast(
                        f"❌ [JobWorker] Pipeline execution failed for content {job.content_id}: {e}",
                        agent="JobWorker"
                    )

        if sync:
            await _execute()
        else:
            asyncio.create_task(_execute())

job_manager = JobManager()
