from enum import Enum
from typing import Set, Dict
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

class InvalidWorkflowTransitionError(Exception):
    pass

class WorkflowState(str, Enum):
    IDEA = "idea"
    RESEARCH = "researching"
    STRATEGY = "strategizing"
    SCRIPT = "scripting"
    SCENES = "planning_scenes"
    ASSETS = "generating_assets"
    VOICE = "generating_voice"
    RENDER = "rendering_video"
    QUALITY_CHECK = "quality_check"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    ANALYTICS = "analyzing_performance"
    FAILED = "failed"

# Map of valid target states for each current state
VALID_TRANSITIONS: Dict[WorkflowState, Set[WorkflowState]] = {
    WorkflowState.IDEA: {WorkflowState.RESEARCH, WorkflowState.FAILED},
    WorkflowState.RESEARCH: {WorkflowState.STRATEGY, WorkflowState.SCRIPT, WorkflowState.FAILED},
    WorkflowState.STRATEGY: {WorkflowState.SCRIPT, WorkflowState.FAILED},
    WorkflowState.SCRIPT: {WorkflowState.SCENES, WorkflowState.FAILED},
    WorkflowState.SCENES: {WorkflowState.ASSETS, WorkflowState.FAILED},
    WorkflowState.ASSETS: {WorkflowState.VOICE, WorkflowState.RENDER, WorkflowState.FAILED},
    WorkflowState.VOICE: {WorkflowState.RENDER, WorkflowState.FAILED},
    WorkflowState.RENDER: {WorkflowState.QUALITY_CHECK, WorkflowState.FAILED},
    WorkflowState.QUALITY_CHECK: {WorkflowState.AWAITING_APPROVAL, WorkflowState.APPROVED, WorkflowState.FAILED},
    WorkflowState.AWAITING_APPROVAL: {WorkflowState.APPROVED, WorkflowState.RESEARCH, WorkflowState.STRATEGY, WorkflowState.SCRIPT, WorkflowState.SCENES, WorkflowState.ASSETS, WorkflowState.VOICE, WorkflowState.FAILED},
    WorkflowState.APPROVED: {WorkflowState.PUBLISHED, WorkflowState.FAILED},
    WorkflowState.PUBLISHED: {WorkflowState.ANALYTICS, WorkflowState.FAILED},
    WorkflowState.ANALYTICS: set(),
    WorkflowState.FAILED: {
        WorkflowState.RESEARCH,
        WorkflowState.STRATEGY,
        WorkflowState.SCRIPT,
        WorkflowState.SCENES,
        WorkflowState.ASSETS,
        WorkflowState.VOICE,
        WorkflowState.RENDER,
        WorkflowState.QUALITY_CHECK
    }
}

def can_transition(from_state: str, to_state: str) -> bool:
    try:
        current = WorkflowState(from_state)
        target = WorkflowState(to_state)
    except ValueError:
        # Permissive fallback for custom string statuses
        return True
    
    if current == target:
        return True
        
    return target in VALID_TRANSITIONS.get(current, set())

async def update_workflow_state(
    db: AsyncSession,
    content_id: uuid.UUID,
    new_state: WorkflowState,
    quality_score: float = None,
    force: bool = False
) -> None:
    from app.db.models import Content as DBContent

    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if content:
        old_state = content.status
        if old_state and old_state != new_state.value and not can_transition(old_state, new_state.value):
            if not force:
                raise InvalidWorkflowTransitionError(
                    f"Illegal state transition requested for content {content_id}: '{old_state}' ➔ '{new_state.value}'."
                )
            else:
                logger.warning(f"Forced administrative state transition: '{old_state}' ➔ '{new_state.value}' for content {content_id}")
        
        content.status = new_state.value
        if quality_score is not None:
            content.quality_score = quality_score
            
        await db.commit()
        await db.refresh(content)
        logger.info(f"Updated content {content_id} status from '{old_state}' to '{new_state.value}'")
