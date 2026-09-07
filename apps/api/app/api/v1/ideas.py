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

@router.delete("/{idea_id}")
async def delete_idea(idea_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContentIdea).filter(DBContentIdea.id == idea_id))
    db_idea = result.scalars().first()
    if db_idea is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    
    await db.delete(db_idea)
    await db.commit()
    return {"ok": True}
