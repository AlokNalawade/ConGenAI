from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Content as DBContent, Research as DBResearch, Script as DBScript
from app.models.schemas import Script
from app.agents.script import ScriptAgent

router = APIRouter()

@router.post("/generate", response_model=Script)
async def generate_script(content_id: uuid.UUID, model: str = None, db: AsyncSession = Depends(get_db)):
    # 1. Fetch content and research
    content_result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = content_result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
        
    research_result = await db.execute(select(DBResearch).filter(DBResearch.content_id == content_id).order_by(DBResearch.created_at.desc()))
    research = research_result.scalars().first()
    if not research:
        raise HTTPException(status_code=400, detail="Research must be generated before script")

    research_data = {
        "summary": research.summary,
        "key_points": research.key_points,
        "hooks": research.hooks
    }
    
    # 2. Run Agent
    agent = ScriptAgent(model=model)
    try:
        script_data = await agent.generate_script(research_data=research_data, platform=content.platform)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Save to DB
    db_script = DBScript(
        content_id=content_id,
        version=1, # simplified versioning for MVP
        hook=script_data.get("hook", ""),
        body=script_data.get("body", ""),
        cta=script_data.get("cta", ""),
        estimated_duration=script_data.get("estimated_duration", 0),
        word_count=script_data.get("word_count", 0),
        status="generated"
    )
    db.add(db_script)
    
    # Update content status
    content.status = "scripting"
    db.add(content)
    
    await db.commit()
    await db.refresh(db_script)
    
    return db_script

@router.get("/", response_model=List[Script])
async def get_scripts(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBScript).filter(DBScript.content_id == content_id))
    return result.scalars().all()
