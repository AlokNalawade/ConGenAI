"""
Approval and moderation endpoints.

Enforces strict state transitions (content must be in AWAITING_APPROVAL)
and provides an audited admin override endpoint for emergency approvals.
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.database import get_db
from app.db.models import (
    Content as DBContent,
    Asset as DBAsset,
    AgentRun as DBAgentRun,
)
from app.workflows.workflow_state import WorkflowState, update_workflow_state

router = APIRouter()


class ForceApproveBody(BaseModel):
    reason: Optional[str] = Field(
        default="Administrative override",
        description="Audit reason explaining why approval was forced.",
    )


@router.post("/approve")
async def approve_content(
    content_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Strict approval endpoint.
    Requires content to be in AWAITING_APPROVAL state with a valid generated video asset.
    """
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    if content.status != WorkflowState.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot approve content with status '{content.status}'. "
                f"Content must be in '{WorkflowState.AWAITING_APPROVAL.value}' state."
            ),
        )

    # Verify a completed video asset exists
    video_res = await db.execute(
        select(DBAsset).filter(
            DBAsset.content_id == content_id,
            DBAsset.asset_type == "video",
            DBAsset.status == "completed",
        )
    )
    if not video_res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot approve content without a completed video asset.",
        )

    await update_workflow_state(db, content_id, WorkflowState.APPROVED, force=False)
    return {
        "content_id": str(content_id),
        "status": WorkflowState.APPROVED.value,
        "message": "Content successfully approved for publishing!",
    }


@router.post("/force-approve")
@router.post("/admin/force-approve")
async def force_approve_content(
    content_id: uuid.UUID,
    body: Optional[ForceApproveBody] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Audited administrative override endpoint.
    Bypasses state validation and records the bypass reason in DBAgentRun for auditability.
    """
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    reason = (body.reason if body else None) or "Administrative override"

    # Audit trail in DBAgentRun
    audit_run = DBAgentRun(
        id=uuid.uuid4(),
        content_id=content_id,
        agent="Admin",
        stage="approval_bypass",
        status="completed",
        error=f"Force approved: {reason}",
        duration_seconds=0.0,
    )
    db.add(audit_run)

    await update_workflow_state(db, content_id, WorkflowState.APPROVED, force=True)
    await db.commit()

    return {
        "content_id": str(content_id),
        "status": WorkflowState.APPROVED.value,
        "message": "Content force-approved via admin bypass.",
        "reason": reason,
    }
