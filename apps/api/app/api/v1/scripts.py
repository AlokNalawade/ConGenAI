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
        "hooks": research.hooks,
        "sources": research.sources,
        "statistics": research.statistics,
        "warnings": research.warnings,
        "content_title": content.title,
        "content_description": content.description,
    }
    
    # 2. Run Agent
    agent = ScriptAgent(model=model)
    try:
        metadata = content.metadata_json or {}
        script_data = await agent.generate_script(
            research_data=research_data,
            platform=content.platform or "Shorts",
            target_duration=content.target_duration or 40,
            target_audience=metadata.get("target_audience", "curious general audience"),
            style=metadata.get("visual_style", "cinematic historical documentary"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Save to DB
    script_dict = script_data.model_dump() if hasattr(script_data, "model_dump") else script_data
    db_script = DBScript(
        content_id=content_id,
        version=1, # simplified versioning for MVP
        hook=script_dict.get("hook", ""),
        body=script_dict.get("body", ""),
        cta=script_dict.get("cta", ""),
        estimated_duration=script_dict.get("estimated_duration", 0),
        word_count=script_dict.get("word_count", 0),
        status="generated"
    )
    db.add(db_script)

    # Persist the full production-ready package without requiring a schema migration.
    # The normalized Script row remains compatible with existing scene/render stages.
    package = script_dict.copy()
    package["version"] = 1
    package["content_id"] = str(content_id)
    content_metadata = dict(content.metadata_json or {})
    content_metadata["script_package"] = package
    content.metadata_json = content_metadata

    # Update content status
    content.status = "scripting"
    db.add(content)
    
    await db.commit()
    await db.refresh(db_script)
    
    response_data = Script.model_validate(db_script).model_dump()
    response_data.update({
        key: script_dict[key]
        for key in (
            "on_screen_captions", "scene_beats", "factual_claims",
            "verification_notes", "caption", "hashtags"
        )
        if key in script_dict
    })
    return response_data

@router.get("/", response_model=List[Script])
async def get_scripts(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBScript).filter(DBScript.content_id == content_id))
    return result.scalars().all()
