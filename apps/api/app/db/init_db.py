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
        
        logger.info("Verifying database table column updates...")
        alter_statements = [
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS parent_asset_id UUID REFERENCES assets(id);",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS pipeline_run_id UUID;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS prompt TEXT;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS negative_prompt TEXT;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS seed INTEGER;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS workflow TEXT;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS sha256 VARCHAR;",
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'completed';",
            "ALTER TABLE research ADD COLUMN IF NOT EXISTS pipeline_run_id UUID;",
            "ALTER TABLE research ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'completed';",
            "ALTER TABLE strategies ADD COLUMN IF NOT EXISTS pipeline_run_id UUID;",
            "ALTER TABLE scripts ADD COLUMN IF NOT EXISTS pipeline_run_id UUID;",
            "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS pipeline_run_id UUID;",
            "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS pipeline_run_id UUID;",
            "ALTER TABLE content ADD COLUMN IF NOT EXISTS batch_id VARCHAR;",
            "ALTER TABLE pipeline_jobs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR;",
            # Sprint 3: heartbeat + idempotency constraint
            "ALTER TABLE pipeline_jobs ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ;",
            "ALTER TABLE pipeline_jobs ALTER COLUMN started_at DROP DEFAULT;",
            "ALTER TABLE pipeline_jobs ALTER COLUMN started_at DROP NOT NULL;",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_job_content_idempotency ON pipeline_jobs(content_id, idempotency_key) WHERE idempotency_key IS NOT NULL;",
        ]
        for stmt in alter_statements:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                logger.warning(f"Column alter statement '{stmt}' skipped: {e}")
        logger.info("Database schema sync completed successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
