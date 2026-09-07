from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Content as DBContent, Script as DBScript, Scene as DBScene
from app.models.schemas import Scene
from app.agents.scene import SceneAgent

router = APIRouter()

@router.post("/generate", response_model=List[Scene])
async def generate_scenes(content_id: uuid.UUID, model: str = None, db: AsyncSession = Depends(get_db)):
    # 1. Fetch content and script
    content_result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = content_result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
        
    script_result = await db.execute(select(DBScript).filter(DBScript.content_id == content_id).order_by(DBScript.created_at.desc()))
    script = script_result.scalars().first()
    if not script:
        raise HTTPException(status_code=400, detail="Script must be generated before scenes")

    script_data = {
        "hook": script.hook,
        "body": script.body,
        "cta": script.cta
    }
    
    # 2. Run Agent
    agent = SceneAgent(model=model)
    try:
        scene_data = await agent.plan_scenes(script_data=script_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Save to DB
    scenes_to_return = []
    for scene_dict in scene_data.get("scenes", []):
        db_scene = DBScene(
            content_id=content_id,
            scene_number=scene_dict.get("scene_number"),
            duration=scene_dict.get("duration"),
            narration=scene_dict.get("narration"),
            visual_description=scene_dict.get("visual_description"),
            visual_prompt=scene_dict.get("visual_prompt"),
            onscreen_text=scene_dict.get("onscreen_text"),
            transition=scene_dict.get("transition"),
            sound_effect=scene_dict.get("sound_effect"),
            status="pending"
        )
        db.add(db_scene)
        scenes_to_return.append(db_scene)
        
    await db.commit()
    for s in scenes_to_return:
        await db.refresh(s)
        
    # Update content status
    content.status = "scenes"
    db.add(content)
    await db.commit()
    
    return scenes_to_return

@router.get("/", response_model=List[Scene])
async def get_scenes(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBScene).filter(DBScene.content_id == content_id).order_by(DBScene.scene_number))
    return result.scalars().all()
