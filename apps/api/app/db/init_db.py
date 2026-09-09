import asyncio
import logging
from sqlalchemy import text
from app.db.database import engine
from app.db.models import Base

logger = logging.getLogger(__name__)

async def init_db():
    async with engine.begin() as conn:
        logger.info("Creating all missing database tables...")
        await conn.run_sync(Base.metadata.create_all)
        
        # Safely add parent_asset_id and version columns to assets table if they do not exist
        logger.info("Verifying assets table column updates...")
        await conn.execute(text("ALTER TABLE assets ADD COLUMN IF NOT EXISTS parent_asset_id UUID REFERENCES assets(id);"))
        await conn.execute(text("ALTER TABLE assets ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;"))
        logger.info("Database schema sync completed successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
