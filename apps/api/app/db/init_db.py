"""
Database initialization and migration orchestration.

Uses Alembic migrations exclusively for both development and production schema management.
Ad-hoc raw ALTER TABLE statements and create_all() schema migrations are strictly prohibited.
"""
import os
import asyncio
import logging
from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_db_initialized = False


def run_migrations_sync():
    """Run Alembic migrations to upgrade the schema to head."""
    # Locate alembic.ini relative to this module: apps/api/alembic.ini
    current_dir = os.path.dirname(os.path.abspath(__file__))  # apps/api/app/db
    api_dir = os.path.dirname(os.path.dirname(current_dir))   # apps/api
    ini_path = os.path.join(api_dir, "alembic.ini")
    if not os.path.exists(ini_path):
        ini_path = os.path.abspath("alembic.ini")

    if not os.path.exists(ini_path):
        raise FileNotFoundError(f"Cannot locate alembic.ini at {ini_path}")

    alembic_cfg = Config(ini_path)
    logger.info("Applying Alembic migrations to head using config: %s", ini_path)
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations completed successfully.")


async def init_db(force: bool = False):
    """
    Ensure the database schema is up to date by executing Alembic migrations.
    Guaranteed to run once per application process unless forced.
    """
    global _db_initialized
    if _db_initialized and not force:
        return
    _db_initialized = True

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, run_migrations_sync)


if __name__ == "__main__":
    asyncio.run(init_db(force=True))
