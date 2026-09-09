import logging
import uuid
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import ContentDNA as DBContentDNA

logger = logging.getLogger(__name__)

class ContentDNAEngine:
    @staticmethod
    async def extract_and_store_dna(
        db: AsyncSession,
        content_id: uuid.UUID,
        topic: str,
        niche: str,
        hook_type: str,
        video_length: float,
        script_structure: str,
        cta: str,
        visual_style: str = "Modern",
        voice: str = "en-US-ChristopherNeural"
    ) -> DBContentDNA:
        dna = DBContentDNA(
            content_id=content_id,
            topic=topic,
            niche=niche,
            hook_type=hook_type,
            video_length=video_length,
            script_structure=script_structure,
            cta=cta,
            visual_style=visual_style,
            voice=voice,
            views=0,
            retention=0.0
        )
        db.add(dna)
        await db.commit()
        await db.refresh(dna)
        logger.info(f"Stored Content DNA record for content {content_id}")
        return dna

    @staticmethod
    async def get_top_performing_dna(db: AsyncSession, limit: int = 5) -> List[DBContentDNA]:
        result = await db.execute(
            select(DBContentDNA).order_by(DBContentDNA.views.desc()).limit(limit)
        )
        return result.scalars().all()
