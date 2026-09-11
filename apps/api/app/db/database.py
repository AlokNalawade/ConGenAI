import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.core.config import settings

engine_kwargs = {"echo": True}
if os.getenv("TESTING", "false").lower() == "true" or os.getenv("PYTEST_CURRENT_TEST"):
    engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, **engine_kwargs)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
AsyncSessionLocal = async_session_maker

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
