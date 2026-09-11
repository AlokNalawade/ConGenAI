from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Content as DBContent, Asset as DBAsset, Script as DBScript
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

@router.get("/videos")
async def list_videos(db: AsyncSession = Depends(get_db)):
    """
    Return all content that has a final video asset, with metadata for the gallery view.
    Single query per table — no N+1. Includes: video path, quality score, script hook,
    platform, status, and creation date for filtering/sorting.
    """
    VIDEO_STATUSES = ("awaiting_approval", "approved", "published", "completed")

    # All content in terminal/ready states, newest first
    content_res = await db.execute(
        select(DBContent)
        .filter(DBContent.status.in_(VIDEO_STATUSES))
        .order_by(DBContent.created_at.desc())
    )
    all_content = content_res.scalars().all()
    if not all_content:
        return []

    content_ids = [c.id for c in all_content]

    # All final video assets for these content items in one query
    # Final video: asset_type="video", scene_id=NULL (scene videos have a scene_id)
    assets_res = await db.execute(
        select(DBAsset).filter(
            DBAsset.content_id.in_(content_ids),
            DBAsset.asset_type == "video",
            DBAsset.scene_id.is_(None),
        )
    )
    all_assets = assets_res.scalars().all()
    # Keep the most recent video per content
    video_by_content = {}
    for a in all_assets:
        cid = str(a.content_id)
        if cid not in video_by_content:
            video_by_content[cid] = a

    # Latest script hook for each content in one query
    scripts_res = await db.execute(
        select(DBScript)
        .filter(DBScript.content_id.in_(content_ids))
        .order_by(DBScript.created_at.desc())
    )
    all_scripts = scripts_res.scalars().all()
    hook_by_content = {}
    for s in all_scripts:
        cid = str(s.content_id)
        if cid not in hook_by_content:
            hook_by_content[cid] = s.hook

    results = []
    for c in all_content:
        cid = str(c.id)
        asset = video_by_content.get(cid)
        if not asset:
            continue  # skip content without a video asset
        results.append({
            "id": cid,
            "title": c.title,
            "status": c.status,
            "platform": c.platform,
            "content_type": c.content_type,
            "quality_score": c.quality_score,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "video_path": asset.path,
            "video_duration": asset.duration,
            "hook": hook_by_content.get(cid),
        })

    return results

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
