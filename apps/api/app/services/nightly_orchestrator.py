"""Persistent multi-channel nightly production orchestration.

Discovery runs once per enabled channel. Each selected idea is converted to a
Content record and dispatched through the existing Redis/arq pipeline worker.
Publishing remains out of scope; the content pipeline's approval gate is kept.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import (
    Channel,
    Content,
    ContentBatch,
    ContentIdea,
    NightlyChannelRun,
    NightlyProductionRun,
    PipelineJobDB,
    PipelineRun,
)
from app.services.opportunity_discovery import OpportunityDiscoveryService
from app.workflows.workflow_state import WorkflowState


ACTIVE_RUN_STATUSES = ("running", "dispatching")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NightlyProductionOrchestrator:
    def __init__(self, discovery_service=None, job_manager=None):
        self.discovery_service = discovery_service or OpportunityDiscoveryService()
        self.job_manager = job_manager

    async def start(
        self,
        db: AsyncSession,
        idempotency_key: str | None = None,
        channel_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, Any]:
        """Create a run and persistent channel allocations, then dispatch."""
        if idempotency_key:
            existing = await db.execute(
                select(NightlyProductionRun).where(
                    NightlyProductionRun.idempotency_key == idempotency_key
                )
            )
            run = existing.scalar_one_or_none()
            if run:
                return await self.refresh_and_serialize(db, run.id)

        query = select(Channel).where(
            Channel.is_active.is_(True), Channel.nightly_enabled.is_(True)
        )
        if channel_ids:
            query = query.where(Channel.id.in_(channel_ids))
        channels = (await db.execute(query.order_by(Channel.name))).scalars().all()
        if channel_ids and len(channels) != len(set(channel_ids)):
            raise ValueError("One or more requested channels are missing, inactive or nightly-disabled")
        if not channels:
            raise ValueError("No active channels are enabled for nightly production")

        total_target = sum(ch.nightly_video_target for ch in channels)
        if total_target > settings.NIGHTLY_MAX_JOBS_PER_RUN:
            raise ValueError(
                f"Nightly target {total_target} exceeds NIGHTLY_MAX_JOBS_PER_RUN "
                f"({settings.NIGHTLY_MAX_JOBS_PER_RUN})"
            )

        # Avoid accidentally starting two overlapping factory runs.
        active = await db.execute(
            select(NightlyProductionRun.id).where(
                NightlyProductionRun.status.in_(ACTIVE_RUN_STATUSES)
            ).limit(1)
        )
        if active.scalar_one_or_none():
            raise RuntimeError("A nightly production run is already active")

        run = NightlyProductionRun(
            id=uuid.uuid4(),
            status="running",
            idempotency_key=idempotency_key,
            requested_total=total_target,
            queued_total=0,
            failed_total=0,
            config_json={
                "channel_ids": [str(ch.id) for ch in channels],
                "channel_targets": {str(ch.id): ch.nightly_video_target for ch in channels},
                "max_jobs": settings.NIGHTLY_MAX_JOBS_PER_RUN,
                "discovery_candidates": settings.NIGHTLY_DISCOVERY_CANDIDATES,
                "approval_required": True,
                "auto_publish": False,
            },
        )
        db.add(run)
        for channel in channels:
            db.add(NightlyChannelRun(
                id=uuid.uuid4(),
                nightly_run_id=run.id,
                channel_id=channel.id,
                target_count=channel.nightly_video_target,
                status="pending",
                content_ids=[],
                job_ids=[],
            ))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if idempotency_key:
                existing = await db.execute(
                    select(NightlyProductionRun).where(
                        NightlyProductionRun.idempotency_key == idempotency_key
                    )
                )
                duplicate = existing.scalar_one_or_none()
                if duplicate:
                    return await self.refresh_and_serialize(db, duplicate.id)
            raise
        await db.refresh(run)

        # Process channels independently; a single failure must not abort other channels.
        for channel_run in (await db.execute(
            select(NightlyChannelRun).where(
                NightlyChannelRun.nightly_run_id == run.id
            ).order_by(NightlyChannelRun.created_at)
        )).scalars().all():
            await self._process_channel(db, run, channel_run)

        await self.refresh_and_serialize(db, run.id)
        return await self.get_status(db, run.id)

    async def _process_channel(
        self, db: AsyncSession, run: NightlyProductionRun, channel_run: NightlyChannelRun
    ) -> None:
        channel = await db.get(Channel, channel_run.channel_id)
        if channel is None:
            channel_run.status = "failed"
            channel_run.failed_count = channel_run.target_count
            channel_run.error = "Channel no longer exists"
            await db.commit()
            return
        channel_run.status = "discovering"
        channel_run.started_at = _utcnow()
        await db.commit()
        try:
            discovery = await self.discovery_service.discover(
                db=db,
                channel=channel,
                candidate_limit=settings.NIGHTLY_DISCOVERY_CANDIDATES,
                select_count=channel_run.target_count,
            )
            channel_run.discovery_json = discovery
            channel_run.selected_count = discovery.get("selected_count", 0)
            if not discovery.get("opportunities"):
                channel_run.status = "partial" if discovery.get("shortfall") else "failed"
                channel_run.failed_count = channel_run.target_count
                channel_run.error = discovery.get("message") or "No qualifying ideas discovered"
                channel_run.completed_at = _utcnow()
                await db.commit()
                return

            selected_ids = [
                uuid.UUID(item["idea_id"])
                for item in discovery["opportunities"]
                if item.get("idea_id")
            ]
            ideas = (await db.execute(
                select(ContentIdea).where(
                    ContentIdea.channel_id == channel.id,
                    ContentIdea.id.in_(selected_ids),
                )
            )).scalars().all()
            if len(ideas) != len(selected_ids):
                raise RuntimeError("Selected ideas could not be reloaded within their channel")

            batch_id = f"night_{uuid.uuid4().hex[:12]}"
            batch = ContentBatch(
                id=batch_id,
                channel_id=channel.id,
                topic=f"Nightly production: {channel.name}",
                requested_count=len(ideas),
                status="queued",
                metadata_json={
                    "nightly_run_id": str(run.id),
                    "nightly_channel_run_id": str(channel_run.id),
                },
            )
            db.add(batch)
            await db.flush()

            created_jobs = []
            for idea in ideas:
                content = Content(
                    idea_id=idea.id,
                    channel_id=channel.id,
                    batch_id=batch_id,
                    title=idea.title,
                    description=idea.description,
                    content_type=idea.content_type or channel.content_format,
                    platform=idea.platform or (channel.platforms or ["youtube_shorts"])[0],
                    target_duration=channel.target_duration_max,
                    status=WorkflowState.IDEA.value,
                    metadata_json={
                        "target_audience": channel.target_audience,
                        "channel_id": str(channel.id),
                        "channel_name": channel.name,
                        "channel_niche": channel.niche,
                        "brand_voice": channel.brand_voice,
                        "visual_style": channel.visual_style,
                        "voice_profile": channel.voice_profile,
                        "content_angle": next(
                            (x.get("content_angle") for x in discovery["opportunities"]
                             if x.get("idea_id") == str(idea.id)), None
                        ),
                        "nightly_run_id": str(run.id),
                        "nightly_channel_run_id": str(channel_run.id),
                    },
                )
                db.add(content)
                await db.flush()
                pipeline_run_id = uuid.uuid4()
                pipeline_run = PipelineRun(
                    id=pipeline_run_id,
                    content_id=content.id,
                    status="queued",
                    current_stage="INIT",
                    is_current=True,
                )
                db.add(pipeline_run)
                job_id = f"job_{uuid.uuid4().hex[:8]}"
                job = PipelineJobDB(
                    id=job_id,
                    content_id=content.id,
                    idempotency_key=f"nightly:{run.id}:{idea.id}",
                    status="queued",
                    current_stage="NEW",
                    progress_percent=0,
                    model_overrides={},
                    resume=0,
                    pipeline_run_id=pipeline_run_id,
                )
                db.add(job)
                created_jobs.append((job_id, content.id, pipeline_run_id))
                channel_run.content_ids = [*(channel_run.content_ids or []), str(content.id)]
                channel_run.job_ids = [*(channel_run.job_ids or []), job_id]

            channel_run.queued_count = len(created_jobs)
            channel_run.failed_count = max(0, channel_run.target_count - len(created_jobs))
            channel_run.status = "dispatching"
            await db.commit()

            # Enqueue only after all records are committed. Existing queue recovery
            # will pick up DB jobs left queued if Redis is temporarily unavailable.
            from app.workflows.task_queue import enqueue_pipeline_job
            dispatch_errors = []
            for job_id, content_id, pipeline_run_id in created_jobs:
                try:
                    await enqueue_pipeline_job(
                        job_id=job_id,
                        content_id=str(content_id),
                        pipeline_run_id=str(pipeline_run_id),
                        model_overrides={},
                        resume=False,
                    )
                except Exception as exc:
                    dispatch_errors.append(f"{job_id}: {exc.__class__.__name__}")
            if dispatch_errors:
                channel_run.error = "Queue dispatch deferred; DB jobs remain recoverable: " + "; ".join(dispatch_errors)
            channel_run.status = "queued" if not channel_run.error else "partial"
            channel_run.completed_at = _utcnow()
            await db.commit()

        except Exception as exc:
            await db.rollback()
            current = await db.get(NightlyChannelRun, channel_run.id)
            if current:
                current.status = "failed"
                current.failed_count = current.target_count
                current.error = f"{exc.__class__.__name__}: {str(exc)[:800]}"
                current.completed_at = _utcnow()
                await db.commit()

    async def refresh_and_serialize(self, db: AsyncSession, run_id: uuid.UUID) -> dict[str, Any]:
        run = await db.get(NightlyProductionRun, run_id)
        if run is None:
            raise ValueError("Nightly production run not found")
        channel_runs = (await db.execute(
            select(NightlyChannelRun).where(NightlyChannelRun.nightly_run_id == run.id)
        )).scalars().all()
        for channel_run in channel_runs:
            if channel_run.job_ids:
                jobs = (await db.execute(
                    select(PipelineJobDB).where(PipelineJobDB.id.in_(channel_run.job_ids))
                )).scalars().all()
                states = {job.id: job.status for job in jobs}
                completed = sum(1 for state in states.values() if state == "completed")
                failed = sum(1 for state in states.values() if state in ("failed", "cancelled"))
                active = any(state in ("queued", "dispatching", "running", "resuming") for state in states.values())
                missing_or_unselected = max(0, channel_run.target_count - len(channel_run.job_ids))
                channel_run.failed_count = max(channel_run.failed_count, failed + missing_or_unselected)
                if active:
                    channel_run.status = "running"
                elif failed or missing_or_unselected:
                    channel_run.status = "partial" if completed or len(jobs) else "failed"
                elif len(jobs) == len(channel_run.job_ids) and completed == len(channel_run.job_ids):
                    channel_run.status = "completed"
                elif len(jobs) < len(channel_run.job_ids):
                    channel_run.status = "partial"
            elif channel_run.status in ("queued", "dispatching"):
                channel_run.status = "failed"
                channel_run.error = channel_run.error or "No pipeline jobs were persisted"
        all_terminal = all(
            item.status in ("completed", "failed", "partial")
            for item in channel_runs
        )
        run.queued_total = sum(item.queued_count for item in channel_runs)
        run.failed_total = sum(item.failed_count for item in channel_runs)
        if all_terminal:
            statuses = {item.status for item in channel_runs}
            run.status = "completed" if statuses == {"completed"} else ("failed" if statuses == {"failed"} else "partial")
            run.completed_at = run.completed_at or _utcnow()
        else:
            run.status = "running"
        await db.commit()
        return self._serialize(run, channel_runs)

    async def get_status(self, db: AsyncSession, run_id: uuid.UUID) -> dict[str, Any]:
        run = await db.get(NightlyProductionRun, run_id)
        if run is None:
            raise ValueError("Nightly production run not found")
        channel_runs = (await db.execute(
            select(NightlyChannelRun).where(
                NightlyChannelRun.nightly_run_id == run.id
            ).order_by(NightlyChannelRun.created_at)
        )).scalars().all()
        return self._serialize(run, channel_runs)

    @staticmethod
    def _serialize(run: NightlyProductionRun, channel_runs: list[NightlyChannelRun]) -> dict[str, Any]:
        return {
            "run_id": str(run.id),
            "status": run.status,
            "requested_total": run.requested_total,
            "queued_total": run.queued_total,
            "failed_total": run.failed_total,
            "approval_required": True,
            "auto_publish": False,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "error": run.error,
            "channels": [
                {
                    "channel_run_id": str(item.id),
                    "channel_id": str(item.channel_id),
                    "target_count": item.target_count,
                    "selected_count": item.selected_count,
                    "queued_count": item.queued_count,
                    "failed_count": item.failed_count,
                    "status": item.status,
                    "content_ids": item.content_ids or [],
                    "job_ids": item.job_ids or [],
                    "discovery": item.discovery_json,
                    "error": item.error,
                }
                for item in channel_runs
            ],
        }
