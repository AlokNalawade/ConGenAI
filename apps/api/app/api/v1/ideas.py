from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import ContentIdea as DBContentIdea, Channel as DBChannel, ChannelTopicHistory
from app.models.schemas import ContentIdea, ContentIdeaCreate, ContentIdeaUpdate
from app.services.llm_service import LLMService
from app.core.config import settings
from app.core.security import require_admin_api_key

router = APIRouter()


@router.get("/available-models", response_model=List[str])
async def get_available_models():
    service = LLMService()
    return await service.get_available_models()


@router.post("/", response_model=ContentIdea)
async def create_idea(idea: ContentIdeaCreate, db: AsyncSession = Depends(get_db)):
    if idea.channel_id is not None and await db.get(DBChannel, idea.channel_id) is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    db_idea = DBContentIdea(**idea.model_dump())
    db.add(db_idea)
    await db.flush()
    if idea.channel_id is not None:
        topic = (idea.topic or idea.title).strip()
        normalized = " ".join(topic.casefold().split())[:300]
        existing = await db.execute(select(ChannelTopicHistory.id).where(
            ChannelTopicHistory.channel_id == idea.channel_id,
            ChannelTopicHistory.normalized_topic == normalized,
        ))
        if existing.scalar_one_or_none() is not None:
            await db.rollback()
            raise HTTPException(status_code=409, detail="This topic is already recorded for the channel")
        db.add(ChannelTopicHistory(
            channel_id=idea.channel_id, normalized_topic=normalized,
            topic=topic, content_idea_id=db_idea.id,
        ))
    await db.commit()
    await db.refresh(db_idea)
    return db_idea


@router.get("/", response_model=List[ContentIdea])
async def read_ideas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    channel_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(DBContentIdea)
    if channel_id is not None:
        query = query.where(DBContentIdea.channel_id == channel_id)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{idea_id}", response_model=ContentIdea)
async def read_idea(idea_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContentIdea).filter(DBContentIdea.id == idea_id))
    idea = result.scalars().first()
    if idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


@router.put("/{idea_id}", response_model=ContentIdea)
async def update_idea(idea_id: uuid.UUID, idea: ContentIdeaUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContentIdea).filter(DBContentIdea.id == idea_id))
    db_idea = result.scalars().first()
    if db_idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")

    updates = idea.model_dump(exclude_unset=True)
    channel_id = updates.get("channel_id", db_idea.channel_id)
    if channel_id is not None and await db.get(DBChannel, channel_id) is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if db_idea.channel_id is not None and channel_id != db_idea.channel_id:
        raise HTTPException(status_code=422, detail="Channel ownership cannot be changed after an idea is assigned")
    for key, value in updates.items():
        setattr(db_idea, key, value)

    if db_idea.channel_id is not None and ("topic" in updates or "title" in updates):
        topic = (updates.get("topic", db_idea.topic) or updates.get("title", db_idea.title) or "").strip()
        normalized = " ".join(topic.casefold().split())[:300]
        if topic:
            existing = await db.execute(select(ChannelTopicHistory).where(
                ChannelTopicHistory.channel_id == db_idea.channel_id,
                ChannelTopicHistory.normalized_topic == normalized,
            ))
            history_entry = existing.scalar_one_or_none()
            if history_entry is not None and history_entry.content_idea_id != db_idea.id:
                await db.rollback()
                raise HTTPException(status_code=409, detail="This topic is already recorded for the channel")
            if history_entry is None:
                db.add(ChannelTopicHistory(
                    channel_id=db_idea.channel_id, normalized_topic=normalized,
                    topic=topic, content_idea_id=db_idea.id,
                ))

    await db.commit()
    await db.refresh(db_idea)
    return db_idea


import os
import glob
from sqlalchemy import delete
from app.db.models import (
    Content as DBContent,
    Asset as DBAsset,
    Scene as DBScene,
    Script as DBScript,
    Strategy as DBStrategy,
    Research as DBResearch,
    AgentRun as DBAgentRun,
    PipelineJobDB,
    PipelineRun as DBPipelineRun,
)


@router.delete("/reset/", dependencies=[Depends(require_admin_api_key)])
async def reset_all_data(db: AsyncSession = Depends(get_db)):
    """Clear all application data and generated media. Admin-only."""
    for subfolder in ("images", "audio", "videos", "subtitles"):
        folder = os.path.join(settings.ASSETS_DIR, subfolder)
        if os.path.exists(folder):
            for file_path in glob.glob(os.path.join(folder, "*")):
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except OSError:
                    pass

    for model_cls in (
        DBAsset,
        DBScene,
        DBScript,
        DBStrategy,
        DBResearch,
        DBAgentRun,
        PipelineJobDB,
        DBPipelineRun,
        DBContent,
        DBContentIdea,
    ):
        await db.execute(delete(model_cls))
    await db.commit()

    # The task queue must use a dedicated Redis DB in production. Do not flush
    # a shared Redis instance from an application reset operation.
    if settings.ENV.lower() != "production":
        try:
            from app.workflows.task_queue import get_redis_pool
            redis_pool = await get_redis_pool()
            if redis_pool:
                await redis_pool.flushdb()
        except Exception:
            pass

    return {"ok": True, "message": "All application data and media assets cleared successfully."}


@router.delete("/{idea_id}")
async def delete_idea(idea_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContentIdea).filter(DBContentIdea.id == idea_id))
    db_idea = result.scalars().first()
    if db_idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    await db.delete(db_idea)
    await db.commit()
    return {"ok": True}
