import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.future import select

from app.db.database import AsyncSessionLocal
from app.db.models import PipelineJobDB
from app.workflows.content_pipeline import ContentPipeline
from app.core.logging import log_manager
from app.core.compute_config import compute_config

logger = logging.getLogger(__name__)

class PipelineJob:
    def __init__(
        self,
        job_id: str,
        content_id: str,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True,
        pipeline_run_id: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ):
        self.job_id = job_id
        self.content_id = content_id
        self.model_overrides = model_overrides or {}
        self.resume = resume
        self.pipeline_run_id = pipeline_run_id or str(uuid.uuid4())
        self.idempotency_key = idempotency_key
        self.status = "queued"
        self.current_stage = "NEW"
        self.progress_percent = 0
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "content_id": self.content_id,
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress_percent": self.progress_percent,
            "model_overrides": self.model_overrides,
            "resume": self.resume,
            "pipeline_run_id": self.pipeline_run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error
        }

class JobManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(JobManager, cls).__new__(cls)
            cls._instance.memory_jobs: Dict[str, PipelineJob] = {}
        return cls._instance

    async def create_job(
        self,
        content_id: str,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True,
        idempotency_key: Optional[str] = None
    ) -> PipelineJob:
        # 1. Idempotency Check: Return active running/queued job if present
        if idempotency_key:
            for j in self.memory_jobs.values():
                if j.idempotency_key == idempotency_key and j.status in ("queued", "running"):
                    logger.info(f"Idempotency hit! Returning existing active job {j.job_id} for key '{idempotency_key}'")
                    return j

            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(PipelineJobDB).filter(
                        PipelineJobDB.idempotency_key == idempotency_key,
                        PipelineJobDB.status.in_(["queued", "running"])
                    )
                )
                existing_db_job = res.scalars().first()
                if existing_db_job:
                    logger.info(f"Idempotency hit in DB! Returning existing active job {existing_db_job.id}")
                    return await self.get_job(existing_db_job.id)

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = PipelineJob(
            job_id=job_id,
            content_id=str(content_id),
            model_overrides=model_overrides,
            resume=resume,
            idempotency_key=idempotency_key
        )
        self.memory_jobs[job_id] = job

        # 2. Mandatory DB Persistence check
        try:
            async with AsyncSessionLocal() as db:
                db_job = PipelineJobDB(
                    id=job.job_id,
                    content_id=uuid.UUID(job.content_id),
                    idempotency_key=job.idempotency_key,
                    status=job.status,
                    current_stage=job.current_stage,
                    progress_percent=job.progress_percent,
                    model_overrides=job.model_overrides,
                    resume=1 if job.resume else 0,
                    pipeline_run_id=uuid.UUID(job.pipeline_run_id)
                )
                db.add(db_job)
                await db.commit()
        except Exception as e:
            if not compute_config.allow_ephemeral_jobs:
                logger.error(f"Mandatory DB persistence failed for job {job_id}: {e}")
                raise RuntimeError(
                    f"Mandatory database job persistence failed for job '{job_id}'. "
                    f"Set ALLOW_EPHEMERAL_JOBS=true to enable ephemeral in-memory fallback. Original error: {e}"
                ) from e
            logger.warning(f"DB job persistence failed, falling back to ephemeral mode (ALLOW_EPHEMERAL_JOBS=true): {e}")

        return job

    async def get_job(self, job_id: str) -> Optional[PipelineJob]:
        if job_id in self.memory_jobs:
            return self.memory_jobs[job_id]
            
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(PipelineJobDB).filter(PipelineJobDB.id == job_id))
            db_job = res.scalars().first()
            if db_job:
                job = PipelineJob(
                    job_id=db_job.id,
                    content_id=str(db_job.content_id),
                    model_overrides=db_job.model_overrides or {},
                    resume=bool(db_job.resume),
                    pipeline_run_id=str(db_job.pipeline_run_id) if db_job.pipeline_run_id else None,
                    idempotency_key=db_job.idempotency_key
                )
                job.status = db_job.status
                job.current_stage = db_job.current_stage
                job.progress_percent = db_job.progress_percent
                job.error = db_job.error
                self.memory_jobs[job_id] = job
                return job
        return None

    async def get_job_by_content(self, content_id: str) -> Optional[PipelineJob]:
        for j in self.memory_jobs.values():
            if j.content_id == str(content_id):
                return j
                
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(PipelineJobDB)
                .filter(PipelineJobDB.content_id == uuid.UUID(str(content_id)))
                .order_by(PipelineJobDB.created_at.desc())
            )
            db_job = res.scalars().first()
            if db_job:
                return await self.get_job(db_job.id)
        return None

    async def update_job_db(self, job: PipelineJob):
        try:
            async with AsyncSessionLocal() as db:
                res = await db.execute(select(PipelineJobDB).filter(PipelineJobDB.id == job.job_id))
                db_job = res.scalars().first()
                if db_job:
                    db_job.status = job.status
                    db_job.current_stage = job.current_stage
                    db_job.progress_percent = job.progress_percent
                    db_job.completed_at = job.completed_at
                    db_job.error = job.error
                    await db.commit()
        except Exception as e:
            logger.warning(f"Could not update status in DB for job {job.job_id}: {e}")

    async def run_job(self, job_id: str, sync: bool = False):
        job = await self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.update_job_db(job)
        
        await log_manager.broadcast(
            f"🚀 [JobWorker] Started pipeline execution for job {job_id} (content: {job.content_id})",
            agent="JobWorker"
        )

        async def _execute():
            async with AsyncSessionLocal() as db:
                pipeline = ContentPipeline()
                try:
                    context = await pipeline.run(
                        content_id=uuid.UUID(job.content_id),
                        db=db,
                        model_overrides=job.model_overrides,
                        resume=job.resume,
                        pipeline_run_id=uuid.UUID(job.pipeline_run_id) if job.pipeline_run_id else None
                    )
                    job.status = "completed"
                    job.current_stage = context.current_state.value
                    job.progress_percent = 100
                    job.completed_at = datetime.utcnow()
                    await self.update_job_db(job)
                    await log_manager.broadcast(
                        f"✅ [JobWorker] Pipeline execution completed for content {job.content_id}",
                        agent="JobWorker"
                    )
                except Exception as e:
                    job.status = "failed"
                    job.error = str(e)
                    job.completed_at = datetime.utcnow()
                    await self.update_job_db(job)
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
