"""
Job management layer — thin DB-only wrapper.

Sprint 3: Removed in-memory job cache and asyncio.create_task().
All job execution goes through the Redis queue (task_queue.py).
"""
import os
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.database import AsyncSessionLocal
from app.db.models import PipelineJobDB, PipelineRun
from app.core.logging import log_manager
from app.core.compute_config import compute_config

logger = logging.getLogger(__name__)


class PipelineJob:
    """
    In-memory representation of a pipeline job.
    Used only for API responses — NOT for execution tracking.
    """

    def __init__(
        self,
        job_id: str,
        content_id: str,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True,
        pipeline_run_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
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
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None  # Issue #5: set on actual execution
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


def _db_to_job(db_job: PipelineJobDB) -> PipelineJob:
    """Convert a DB row to a PipelineJob object for API responses."""
    job = PipelineJob(
        job_id=db_job.id,
        content_id=str(db_job.content_id),
        model_overrides=db_job.model_overrides or {},
        resume=bool(db_job.resume),
        pipeline_run_id=str(db_job.pipeline_run_id) if db_job.pipeline_run_id else None,
        idempotency_key=db_job.idempotency_key,
    )
    job.status = db_job.status
    job.current_stage = db_job.current_stage
    job.progress_percent = db_job.progress_percent
    job.started_at = db_job.started_at
    job.completed_at = db_job.completed_at
    job.created_at = db_job.created_at
    job.error = db_job.error
    return job


class JobManager:
    """
    DB-only job manager. No in-memory cache. No asyncio.create_task().
    
    create_job() persists to PostgreSQL and enqueues to Redis.
    get_job() / get_job_by_content() always read from PostgreSQL.
    """

    async def create_job(
        self,
        content_id: str,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True,
        idempotency_key: Optional[str] = None,
        enqueue: bool = True,
        pipeline_run_id: Optional[str] = None,
    ) -> PipelineJob:
        """
        Create a new pipeline job in the DB and enqueue it to Redis.

        pipeline_run_id: if provided, reuses an existing run ID (used by visuals-only
        regeneration to resume the same run after clearing its media assets).

        Issue #4: Uses INSERT with ON CONFLICT for race-safe idempotency.
        """
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        pipeline_run_id = pipeline_run_id or str(uuid.uuid4())

        job = PipelineJob(
            job_id=job_id,
            content_id=str(content_id),
            model_overrides=model_overrides,
            resume=resume,
            pipeline_run_id=pipeline_run_id,
            idempotency_key=idempotency_key,
        )

        run_uuid = uuid.UUID(job.pipeline_run_id)
        content_uuid = uuid.UUID(job.content_id)

        async with AsyncSessionLocal() as db:
            # 1. Guarantee PipelineRun exists to satisfy Foreign Key constraint
            existing_run = await db.get(PipelineRun, run_uuid)
            if not existing_run:
                db_run = PipelineRun(
                    id=run_uuid,
                    content_id=content_uuid,
                    status="queued",
                    current_stage="INIT",
                    is_current=True,
                )
                db.add(db_run)
                await db.flush()

            # 2. Insert PipelineJobDB
            db_job = PipelineJobDB(
                id=job.job_id,
                content_id=content_uuid,
                idempotency_key=job.idempotency_key,
                status=job.status,
                current_stage=job.current_stage,
                progress_percent=job.progress_percent,
                model_overrides=job.model_overrides,
                resume=1 if job.resume else 0,
                pipeline_run_id=run_uuid,
            )
            try:
                db.add(db_job)
                await db.commit()
                logger.info(f"Created pipeline job {job_id} in DB")
            except IntegrityError:
                # Idempotency constraint or active job constraint hit — return existing job
                await db.rollback()
                if idempotency_key:
                    result = await db.execute(
                        select(PipelineJobDB).filter(
                            PipelineJobDB.content_id == content_uuid,
                            PipelineJobDB.idempotency_key == idempotency_key,
                        )
                    )
                    existing = result.scalars().first()
                    if existing:
                        logger.info(
                            f"Idempotency hit (DB constraint): returning existing job {existing.id}"
                        )
                        return _db_to_job(existing)
                # Check if partial unique index for active job was triggered
                active = await self.get_active_job_by_content(str(content_id))
                if active:
                    logger.info(
                        f"Active job collision (DB constraint): returning existing active job {active.job_id}"
                    )
                    return active
                raise

        # Enqueue to Redis queue unless testing or enqueue=False
        if enqueue and os.getenv("TESTING", "false").lower() not in ("true", "1"):
            try:
                from app.workflows.task_queue import enqueue_pipeline_job

                await enqueue_pipeline_job(
                    job_id=job.job_id,
                    content_id=job.content_id,
                    pipeline_run_id=job.pipeline_run_id,
                    model_overrides=job.model_overrides,
                    resume=job.resume,
                )
            except Exception as e:
                logger.warning(f"Redis enqueue failed for job {job.job_id}: {e}")
                # Job is persisted in DB — stale recovery will pick it up
                if not compute_config.allow_ephemeral_jobs:
                    raise

        return job

    async def get_job(self, job_id: str) -> Optional[PipelineJob]:
        """
        Get a job by ID. Always reads from DB (Issue #6: no stale memory cache).
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PipelineJobDB).filter(PipelineJobDB.id == job_id)
            )
            db_job = result.scalars().first()
            if db_job:
                return _db_to_job(db_job)
        return None

    async def get_job_by_content(self, content_id: str) -> Optional[PipelineJob]:
        """
        Get the most recent job for a content ID.
        Issue #6: Always queries DB first, returns latest job.
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PipelineJobDB)
                .filter(PipelineJobDB.content_id == uuid.UUID(str(content_id)))
                .order_by(PipelineJobDB.created_at.desc())
            )
            db_job = result.scalars().first()
            if db_job:
                return _db_to_job(db_job)
        return None

    async def get_active_job_by_content(self, content_id: str) -> Optional[PipelineJob]:
        """
        Get the currently active (queued or running) job for a content ID.
        Used to prevent race conditions (e.g. concurrent regenerations or duplicate runs).
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(PipelineJobDB)
                .filter(
                    PipelineJobDB.content_id == uuid.UUID(str(content_id)),
                    PipelineJobDB.status.in_(["queued", "running"]),
                )
                .order_by(PipelineJobDB.created_at.desc())
            )
            db_job = result.scalars().first()
            if db_job:
                return _db_to_job(db_job)
        return None

    async def run_job_inline(self, job_id: str):
        """
        Execute a job synchronously (inline) — for tests only.
        In production, jobs are executed by the arq worker process.
        """
        from app.workflows.task_queue import execute_pipeline_job

        job = await self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        await execute_pipeline_job(
            ctx={},
            job_id=job.job_id,
            content_id=job.content_id,
            pipeline_run_id=job.pipeline_run_id,
            model_overrides=job.model_overrides,
            resume=job.resume,
        )


# Module-level singleton
job_manager = JobManager()
