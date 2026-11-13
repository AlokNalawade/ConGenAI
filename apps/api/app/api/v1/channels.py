from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.db.database import get_db
from app.db.models import Channel as DBChannel
from app.models.schemas import Channel, ChannelCreate, ChannelUpdate

router = APIRouter()


@router.post("/", response_model=Channel, status_code=201)
async def create_channel(channel: ChannelCreate, db: AsyncSession = Depends(get_db)):
    if (channel.target_duration_min is not None and channel.target_duration_max is not None
            and channel.target_duration_min > channel.target_duration_max):
        raise HTTPException(status_code=422, detail="target_duration_min cannot exceed target_duration_max")
    db_channel = DBChannel(**channel.model_dump())
    db.add(db_channel)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A channel with this slug already exists")
    await db.refresh(db_channel)
    return db_channel


@router.get("/", response_model=List[Channel])
async def list_channels(
    active_only: bool = Query(False),
    nightly_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    query = select(DBChannel)
    if active_only:
        query = query.where(DBChannel.is_active.is_(True))
    if nightly_only:
        query = query.where(DBChannel.is_active.is_(True), DBChannel.nightly_enabled.is_(True))
    result = await db.execute(query.order_by(DBChannel.name).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/nightly-summary")
async def nightly_summary(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DBChannel).where(
            DBChannel.is_active.is_(True), DBChannel.nightly_enabled.is_(True)
        )
    )
    channels = result.scalars().all()
    return {
        "enabled_channel_count": len(channels),
        "nightly_video_target": sum(channel.nightly_video_target for channel in channels),
        "channels": [
            {"channel_id": str(channel.id), "name": channel.name,
             "niche": channel.niche, "nightly_video_target": channel.nightly_video_target}
            for channel in channels
        ],
    }


@router.get("/{channel_id}", response_model=Channel)
async def get_channel(channel_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    channel = await db.get(DBChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


@router.patch("/{channel_id}", response_model=Channel)
async def update_channel(
    channel_id: uuid.UUID,
    updates: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
):
    channel = await db.get(DBChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    values = updates.model_dump(exclude_unset=True)
    minimum = values.get("target_duration_min", channel.target_duration_min)
    maximum = values.get("target_duration_max", channel.target_duration_max)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(status_code=422, detail="target_duration_min cannot exceed target_duration_max")
    for key, value in values.items():
        setattr(channel, key, value)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A channel with this slug already exists")
    await db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=204)
async def deactivate_channel(channel_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Soft-deactivate a channel so historical ideas and content retain ownership."""
    channel = await db.get(DBChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel.is_active = False
    channel.nightly_enabled = False
    await db.commit()
    return None
