import time
import logging
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import AsyncSessionLocal
from app.db.models import AgentRun as DBAgentRun

logger = logging.getLogger(__name__)

class AgentTracker:
    def __init__(
        self,
        db: Optional[AsyncSession],
        content_id: uuid.UUID,
        stage: str,
        agent_name: str,
        provider: str = "ollama",
        model: str = "llama3:latest",
        prompt_version: int = 1
    ):
        self.db = db
        self.content_id = content_id
        self.stage = stage
        self.agent_name = agent_name
        self.provider = provider
        self.model = model
        self.prompt_version = prompt_version
        self.start_time: float = 0.0
        self.duration_seconds: float = 0.0
        self.status = "started"
        self.error: Optional[str] = None
        self.input_tokens = 0
        self.output_tokens = 0

    async def __aenter__(self):
        self.start_time = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.duration_seconds = time.time() - self.start_time
        if exc_val is not None:
            self.status = "failed"
            self.error = str(exc_val)
        else:
            self.status = "success"

        try:
            async with AsyncSessionLocal() as session:
                agent_run = DBAgentRun(
                    id=uuid.uuid4(),
                    content_id=self.content_id,
                    stage=self.stage,
                    agent=self.agent_name,
                    provider=self.provider,
                    model=self.model,
                    prompt_version=self.prompt_version,
                    duration_seconds=self.duration_seconds,
                    status=self.status,
                    error=self.error,
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    cost=0.0
                )
                session.add(agent_run)
                await session.commit()
                logger.info(f"Recorded AgentRun for {self.agent_name} ({self.stage}) in {self.duration_seconds:.2f}s [status: {self.status}]")
        except Exception as e:
            logger.error(f"Failed to record AgentRun telemetry: {e}")
