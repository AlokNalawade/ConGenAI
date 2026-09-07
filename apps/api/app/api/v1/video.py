from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Scene as DBScene, Asset as DBAsset, Content as DBContent
from app.models.schemas import Asset
from app.agents.video import VideoAgent

router = APIRouter()

@router.post("/generate", response_model=Asset)
async def generate_video(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # 1. Fetch scenes for this content
    result = await db.execute(select(DBScene).filter(DBScene.content_id == content_id).order_by(DBScene.scene_number))
    scenes = result.scalars().all()
    
    if not scenes:
        raise HTTPException(status_code=400, detail="No scenes found for this content")
        
    agent = VideoAgent()
    scene_video_paths = []
    
    # 2. For each scene, find its image and audio, then create a scene video
    for scene in scenes:
        assets_res = await db.execute(select(DBAsset).filter(DBAsset.scene_id == scene.id))
        assets = assets_res.scalars().all()
        
        image_asset = next((a for a in assets if a.asset_type == "image"), None)
        audio_asset = next((a for a in assets if a.asset_type == "audio"), None)
        
        if not image_asset or not audio_asset:
            raise HTTPException(status_code=400, detail=f"Scene {scene.id} is missing image or audio asset")
            
        try:
            scene_vid_path = await agent.assemble_scene(image_asset.path, audio_asset.path, scene.onscreen_text)
            scene_video_paths.append(scene_vid_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error rendering scene {scene.id}: {str(e)}")
            
    # 3. Concatenate all scene videos
    try:
        final_video_path = await agent.assemble_final(scene_video_paths)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error concatenating final video: {str(e)}")
        
    # 4. Save to DB
    db_asset = DBAsset(
        content_id=content_id,
        asset_type="video",
        path=final_video_path,
        mime_type="video/mp4",
        provider="ffmpeg",
        model="local"
    )
    db.add(db_asset)
    
    # Update content status
    content_result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = content_result.scalars().first()
    if content:
        content.status = "completed"
        db.add(content)
        
    await db.commit()
    await db.refresh(db_asset)
    
    return db_asset
