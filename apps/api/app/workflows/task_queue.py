"""
Redis-backed task queue using arq for durable pipeline job execution.

Architecture:
  FastAPI API → enqueue_pipeline_job() → Redis → arq Worker → ContentPipeline
  
Run the worker as a separate process:
  PYTHONPATH=apps/api python -m app.workflows.task_queue
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict

from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from sqlalchemy import update, func
from sqlalchemy.future import select

from app.core.config import settings
from app.core.compute_config import compute_config
from app.core.logging import log_manager
from app.db.database import AsyncSessionLocal
from app.db.models import PipelineJobDB, PipelineRun as DBPipelineRun
from app.workflows.content_pipeline import ContentPipeline

logger = logging.getLogger(__name__)

# --- Redis connection ---

_redis_pool: Optional[ArqRedis] = None


async def get_redis_pool() -> ArqRedis:
    """Get or create the arq Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(
            RedisSettings(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                database=settings.REDIS_DB,
            )
        )
    return _redis_pool


async def close_redis_pool():
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


# --- Enqueue ---

async def enqueue_pipeline_job(
    job_id: str,
    content_id: str,
    pipeline_run_id: str,
    model_overrides: Optional[Dict[str, str]] = None,
    resume: bool = True,
) -> str:
    """
    Enqueue a pipeline job into the Redis queue.
    Called by the API layer after creating the PipelineJobDB record.
    Returns the arq job ID.
    """
    pool = await get_redis_pool()
    arq_job = await pool.enqueue_job(
        "execute_pipeline_job",
        job_id=job_id,
        content_id=content_id,
        pipeline_run_id=pipeline_run_id,
        model_overrides=model_overrides or {},
        resume=resume,
    )
    logger.info(f"Enqueued pipeline job {job_id} to Redis (arq_id={arq_job.job_id})")
    return arq_job.job_id


# --- Worker function ---

async def execute_pipeline_job(
    ctx: dict,
    *,
    job_id: str,
    content_id: str,
    pipeline_run_id: str,
    model_overrides: Dict[str, str],
    resume: bool,
):
    """
    arq worker function. Runs ContentPipeline for the given job.
    This runs in the worker process, NOT in the API process.
    """
    logger.info(f"Worker executing pipeline job {job_id} (content={content_id}, resume={resume})")

    # Mark job as running + set started_at
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(PipelineJobDB)
            .where(PipelineJobDB.id == job_id)
            .values(
                status="running",
                started_at=func.now(),
                last_heartbeat=func.now(),
            )
        )
        await db.commit()

    # Start heartbeat loop
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(job_id, compute_config.worker_heartbeat_seconds)
    )

    try:
        async with AsyncSessionLocal() as db:
            pipeline = ContentPipeline()
            context = await pipeline.run(
                content_id=uuid.UUID(content_id),
                db=db,
                model_overrides=model_overrides,
                resume=resume,
                pipeline_run_id=uuid.UUID(pipeline_run_id),
            )

        # Mark job completed
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(PipelineJobDB)
                .where(PipelineJobDB.id == job_id)
                .values(
                    status="completed",
                    current_stage=context.current_state.value,
                    progress_percent=100,
                    completed_at=func.now(),
                    last_heartbeat=func.now(),
                )
            )
            await db.commit()

        await log_manager.broadcast(
            f"✅ [Worker] Pipeline job {job_id} completed for content {content_id}",
            agent="Worker",
        )

    except Exception as e:
        logger.error(f"Worker job {job_id} failed: {e}", exc_info=True)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(PipelineJobDB)
                .where(PipelineJobDB.id == job_id)
                .values(
                    status="failed",
                    error=str(e)[:2000],
                    completed_at=func.now(),
                    last_heartbeat=func.now(),
                )
            )
            await db.commit()

        await log_manager.broadcast(
            f"❌ [Worker] Pipeline job {job_id} failed: {e}",
            agent="Worker",
        )
        raise

    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


# --- Heartbeat ---

async def _heartbeat_loop(job_id: str, interval: int = 30):
    """Updates last_heartbeat every N seconds so stale-job recovery knows we're alive."""
    while True:
        await asyncio.sleep(interval)
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(PipelineJobDB)
                    .where(PipelineJobDB.id == job_id)
                    .values(last_heartbeat=func.now())
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Heartbeat update failed for job {job_id}: {e}")


# --- Stale Job Recovery ---

async def recover_stale_jobs():
    """
    Find jobs marked 'running' whose heartbeat is stale and re-enqueue them.
    Called on worker startup.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=compute_config.stale_job_timeout_seconds)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PipelineJobDB).filter(
                PipelineJobDB.status == "running",
                PipelineJobDB.last_heartbeat < cutoff,
            )
        )
        stale_jobs = result.scalars().all()

        if not stale_jobs:
            logger.info("No stale jobs found on startup.")
            return

        logger.warning(f"Found {len(stale_jobs)} stale jobs — re-enqueueing...")
        for job in stale_jobs:
            job.status = "queued"
            job.error = f"Re-queued: heartbeat stale since {job.last_heartbeat}"
        await db.commit()

    # Re-enqueue after committing status change
    for job in stale_jobs:
        try:
            await enqueue_pipeline_job(
                job_id=job.id,
                content_id=str(job.content_id),
                pipeline_run_id=str(job.pipeline_run_id) if job.pipeline_run_id else str(uuid.uuid4()),
                model_overrides=job.model_overrides or {},
                resume=bool(job.resume),
            )
            logger.info(f"Re-enqueued stale job {job.id}")
        except Exception as e:
            logger.error(f"Failed to re-enqueue stale job {job.id}: {e}")


# --- Startup hook ---

async def on_worker_startup(ctx: dict):
    """Called once when the arq worker process starts."""
    logger.info("arq worker starting — recovering stale jobs...")
    from app.db.init_db import init_db
    await init_db()
    await recover_stale_jobs()
    logger.info("arq worker ready.")


async def on_worker_shutdown(ctx: dict):
    """Called when the arq worker process stops."""
    logger.info("arq worker shutting down...")
    await close_redis_pool()


# --- arq WorkerSettings (entrypoint for `python -m app.workflows.task_queue`) ---

class WorkerSettings:
    """arq worker configuration. Run with: arq app.workflows.task_queue.WorkerSettings"""
    functions = [execute_pipeline_job]
    on_startup = on_worker_startup
    on_shutdown = on_worker_shutdown
    max_jobs = compute_config.max_concurrent_jobs
    job_timeout = 1800  # 30 minutes max per pipeline job
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
    )


if __name__ == "__main__":
    # Allow running as: PYTHONPATH=apps/api python -m app.workflows.task_queue
    from arq.cli import cli
    import sys
    sys.argv = ["arq", "app.workflows.task_queue.WorkerSettings"]
    cli()
