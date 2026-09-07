from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Scene as DBScene, Asset as DBAsset
from app.models.schemas import Asset
from app.agents.image import ImageAgent
from app.agents.voice import VoiceAgent

router = APIRouter()

@router.post("/scenes/{scene_id}/image", response_model=Asset)
async def generate_scene_image(scene_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # 1. Fetch scene
    result = await db.execute(select(DBScene).filter(DBScene.id == scene_id))
    scene = result.scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
        
    # 2. Run Agent
    agent = ImageAgent()
    try:
        caption = scene.onscreen_text or scene.narration
        image_path = await agent.generate(
            prompt=scene.visual_prompt or scene.visual_description,
            caption_text=caption
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Save to DB
    db_asset = DBAsset(
        content_id=scene.content_id,
        scene_id=scene_id,
        asset_type="image",
        path=image_path,
        mime_type="image/jpeg",
        provider="mock",
        model="mock-sd"
    )
    db.add(db_asset)
    
    scene.status = "image_generated"
    await db.commit()
    await db.refresh(db_asset)
    
    return db_asset

@router.post("/scenes/{scene_id}/voice", response_model=Asset)
async def generate_scene_voice(scene_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # 1. Fetch scene
    result = await db.execute(select(DBScene).filter(DBScene.id == scene_id))
    scene = result.scalars().first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
        
    if not scene.narration:
        scene.narration = f"Scene {scene.scene_number}: {scene.visual_description or 'AI short video content.'}"
        
    # 2. Run Agent
    agent = VoiceAgent()
    try:
        voice_path = await agent.generate(text=scene.narration)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 3. Save to DB
    db_asset = DBAsset(
        content_id=scene.content_id,
        scene_id=scene_id,
        asset_type="audio",
        path=voice_path,
        mime_type="audio/mpeg",
        provider="edge-tts",
        model="en-US-ChristopherNeural"
    )
    db.add(db_asset)
    
    scene.status = "audio_generated"
    await db.commit()
    await db.refresh(db_asset)
    
    return db_asset

@router.get("/content/{content_id}/assets", response_model=List[Asset])
async def get_assets(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBAsset).filter(DBAsset.content_id == content_id))
    return result.scalars().all()
