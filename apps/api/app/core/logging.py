"""
Live Agent Terminal — log broadcasting via Redis pub/sub.

Architecture:
  Worker process  →  log_manager.broadcast()
                  →  Redis PUBLISH "pipeline:logs" JSON
                  →  API process subscriber task
                  →  all active WebSocket connections  →  browser terminal

Fallback (Redis unavailable / TESTING mode):
  broadcast() pushes directly to in-process WebSocket connections.
  This keeps local dev (no Redis) and tests working without changes.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import List

from fastapi import WebSocket

logger = logging.getLogger(__name__)

REDIS_CHANNEL = "pipeline:logs"


class LogManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str, agent: str = "System"):
        """
        Publish a log message.

        - If Redis is reachable: publish to the 'pipeline:logs' pub/sub channel.
          The API process subscriber task will pick it up and push to all WebSocket clients.
          This works across processes (arq worker → API → browser).

        - If Redis is unavailable (local dev / tests): push directly to the in-process
          WebSocket connection list. Works when everything runs in one process.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [{agent}] {message}"
        print(formatted)

        payload = json.dumps({"agent": agent, "message": message, "time": timestamp})

        # Try Redis pub/sub first (cross-process broadcast)
        if not os.getenv("TESTING"):
            try:
                from app.core.config import settings
                import redis.asyncio as aioredis
                r = aioredis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=settings.REDIS_DB,
                    socket_connect_timeout=0.2,
                    socket_timeout=0.2,
                )
                await r.publish(REDIS_CHANNEL, payload)
                await r.aclose()
                return
            except Exception as exc:
                # Redis down — fall through to direct WebSocket push
                logger.debug(f"Redis pub/sub unavailable ({exc}), broadcasting directly to WebSocket clients.")

        # Direct in-process push (local dev without Redis, or TESTING mode)
        await self._push_to_websockets(payload)

    async def _push_to_websockets(self, payload: str):
        """Push a pre-serialised JSON payload directly to all connected WebSocket clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect(connection)


log_manager = LogManager()


async def redis_subscriber_task():
    """
    Long-running background task that runs in the API process.

    Subscribes to the 'pipeline:logs' Redis pub/sub channel.
    Every message published by any worker process is fanned out to
    all connected WebSocket clients via log_manager.active_connections.

    Started by FastAPI's lifespan event on startup.
    Automatically reconnects with exponential backoff if Redis drops.
    """
    from app.core.config import settings
    import redis.asyncio as aioredis

    backoff = 1
    while True:
        try:
            r = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
            )
            pubsub = r.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)
            logger.info(f"[LogManager] Subscribed to Redis channel '{REDIS_CHANNEL}'")
            backoff = 1  # reset on successful connect

            async for raw in pubsub.listen():
                if raw["type"] != "message":
                    continue
                payload = raw["data"]
                if isinstance(payload, bytes):
                    payload = payload.decode()
                await log_manager._push_to_websockets(payload)

        except asyncio.CancelledError:
            logger.info("[LogManager] Redis subscriber task cancelled.")
            return
        except Exception as exc:
            logger.warning(
                f"[LogManager] Redis subscriber disconnected ({exc}). "
                f"Retrying in {backoff}s..."
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)  # cap at 30s
