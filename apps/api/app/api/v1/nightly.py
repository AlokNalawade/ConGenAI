"""API controls for one-click nightly content-factory runs."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import NightlyProductionRun
from app.services.nightly_orchestrator import NightlyProductionOrchestrator

router = APIRouter()


class NightlyRunRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    channel_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


@router.post("/run", status_code=202)
async def start_nightly_run(
    request: NightlyRunRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Start discovery and queue production for every enabled channel."""
    request = request or NightlyRunRequest()
    try:
        orchestrator = NightlyProductionOrchestrator()
        result = await orchestrator.start(
            db,
            idempotency_key=request.idempotency_key,
            channel_ids=request.channel_ids,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs")
async def list_nightly_runs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(NightlyProductionRun)
        .order_by(NightlyProductionRun.created_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()
    orchestrator = NightlyProductionOrchestrator()
    output = []
    for run in runs:
        # Recalculate from authoritative pipeline job rows before presenting.
        output.append(await orchestrator.refresh_and_serialize(db, run.id))
    return output


@router.get("/runs/{run_id}")
async def get_nightly_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        orchestrator = NightlyProductionOrchestrator()
        await orchestrator.refresh_and_serialize(db, run_id)
        return await orchestrator.get_status(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
