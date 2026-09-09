from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Content as DBContent, Research as DBResearch
from app.models.schemas import Research, ResearchCreate
from app.agents.research import ResearchAgent

router = APIRouter()

@router.post("/", response_model=Research)
async def generate_research(content_id: uuid.UUID, model: str = None, db: AsyncSession = Depends(get_db)):
    # 1. Fetch content and idea
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
        
    topic = content.title or "Unknown Topic"
    target_audience = "General" # Ideally from idea
    platform = content.platform or "Shorts"

    # 2. Run Agent
    agent = ResearchAgent(model=model)
    try:
        research_data = await agent.research_topic(topic=topic, target_audience=target_audience, platform=platform)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Save to DB
    res_dict = research_data.model_dump() if hasattr(research_data, "model_dump") else research_data
    db_research = DBResearch(
        content_id=content_id,
        summary=res_dict.get("summary", ""),
        key_points=res_dict.get("key_points", []),
        statistics=res_dict.get("statistics", []),
        sources=res_dict.get("sources", []),
        competitor_analysis=res_dict.get("competitor_analysis", []),
        hooks=res_dict.get("hooks", []),
        warnings=res_dict.get("warnings", []),
    )
    db.add(db_research)
    
    # Update content status
    content.status = "researching"
    db.add(content)
    
    await db.commit()
    await db.refresh(db_research)
    
    return db_research

@router.get("/", response_model=List[Research])
async def get_research(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBResearch).filter(DBResearch.content_id == content_id))
    return result.scalars().all()
