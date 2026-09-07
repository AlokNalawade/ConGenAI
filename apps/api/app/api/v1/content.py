from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Content as DBContent
from app.models.schemas import Content, ContentCreate, ContentUpdate

router = APIRouter()

@router.post("/", response_model=Content)
async def create_content(content: ContentCreate, db: AsyncSession = Depends(get_db)):
    db_content = DBContent(**content.model_dump())
    db.add(db_content)
    await db.commit()
    await db.refresh(db_content)
    return db_content

@router.get("/", response_model=List[Content])
async def read_contents(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).offset(skip).limit(limit))
    contents = result.scalars().all()
    return contents

@router.get("/{content_id}", response_model=Content)
async def read_content(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if content is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return content

@router.put("/{content_id}", response_model=Content)
async def update_content(content_id: uuid.UUID, content: ContentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    db_content = result.scalars().first()
    if db_content is None:
        raise HTTPException(status_code=404, detail="Content not found")
    
    update_data = content.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_content, key, value)
        
    await db.commit()
    await db.refresh(db_content)
    return db_content

@router.delete("/{content_id}")
async def delete_content(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    db_content = result.scalars().first()
    if db_content is None:
        raise HTTPException(status_code=404, detail="Content not found")
    
    await db.delete(db_content)
    await db.commit()
    return {"ok": True}
