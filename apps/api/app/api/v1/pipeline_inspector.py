"""
Pipeline inspector endpoint.

Provides comprehensive stage-by-stage inspection for any content item
using the unified PipelineSnapshotService.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.pipeline_snapshot_service import PipelineSnapshotService

router = APIRouter()


@router.get("/inspect")
async def inspect_pipeline(
    content_id: uuid.UUID,
    run_id: Optional[uuid.UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Return all pipeline stage data for a content item in one call.
    Resolves the canonical run by default, or accepts an explicit run_id.
    """
    snapshot = await PipelineSnapshotService.get_snapshot(db, content_id, run_id=run_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Content not found")

    return snapshot
