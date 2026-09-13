from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import ContentIdea as DBContentIdea
from app.models.schemas import ContentIdea, ContentIdeaCreate, ContentIdeaUpdate

from app.services.llm_service import LLMService

router = APIRouter()

@router.get("/available-models", response_model=List[str])
async def get_available_models():
    service = LLMService()
    return await service.get_available_models()

@router.post("/", response_model=ContentIdea)
async def create_idea(idea: ContentIdeaCreate, db: AsyncSession = Depends(get_db)):
    db_idea = DBContentIdea(**idea.model_dump())
    db.add(db_idea)
    await db.commit()
    await db.refresh(db_idea)
    return db_idea

@router.get("/", response_model=List[ContentIdea])
async def read_ideas(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContentIdea).offset(skip).limit(limit))
    ideas = result.scalars().all()
    return ideas

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
    
    update_data = idea.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_idea, key, value)
        
    await db.commit()
    await db.refresh(db_idea)
    return db_idea

import os
import glob
from sqlalchemy import delete
from app.core.config import settings
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

@router.delete("/reset/")
async def reset_all_data(db: AsyncSession = Depends(get_db)):
    """
    Clears all database tables and removes all generated media assets from disk.
    """
    # 1. Clean disk assets
    for subfolder in ("images", "audio", "videos", "subtitles"):
        folder = os.path.join(settings.ASSETS_DIR, subfolder)
        if os.path.exists(folder):
            for file_path in glob.glob(os.path.join(folder, "*")):
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except OSError:
                    pass

    # 2. Clean database tables
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
    return {"ok": True, "message": "All data and media assets cleared successfully."}

@router.delete("/{idea_id}")
async def delete_idea(idea_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContentIdea).filter(DBContentIdea.id == idea_id))
    db_idea = result.scalars().first()
    if db_idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    await db.delete(db_idea)
    await db.commit()
    return {"ok": True}
