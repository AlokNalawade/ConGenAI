import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.core.config import settings
from app.api.v1 import ideas, content, research, scripts, scenes, assets, video, pipeline, experiments


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup, cancel them on shutdown."""
    tasks = []
    if not os.getenv("TESTING"):
        from app.core.logging import redis_subscriber_task
        tasks.append(asyncio.create_task(redis_subscriber_task()))

    yield

    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/health")
def health_check():
    return {"status": "ok", "project": settings.PROJECT_NAME}


app.include_router(ideas.router, prefix=f"{settings.API_V1_STR}/ideas", tags=["ideas"])
app.include_router(content.router, prefix=f"{settings.API_V1_STR}/content", tags=["content"])
app.include_router(pipeline.router, prefix=f"{settings.API_V1_STR}/content/{{content_id}}", tags=["pipeline"])
app.include_router(research.router, prefix=f"{settings.API_V1_STR}/content/{{content_id}}/research", tags=["research"])
app.include_router(scripts.router, prefix=f"{settings.API_V1_STR}/content/{{content_id}}/scripts", tags=["scripts"])
app.include_router(scenes.router, prefix=f"{settings.API_V1_STR}/content/{{content_id}}/scenes", tags=["scenes"])
app.include_router(assets.router, prefix=f"{settings.API_V1_STR}", tags=["assets"])
app.include_router(video.router, prefix=f"{settings.API_V1_STR}/content/{{content_id}}/video", tags=["video"])
app.include_router(experiments.router, prefix=f"{settings.API_V1_STR}/experiments", tags=["experiments"])


from app.core.logging import log_manager


@app.websocket("/api/ws/logs")
async def websocket_logs(websocket: WebSocket):
    # Browser WebSocket cannot attach arbitrary Authorization headers, so the
    # admin key is accepted as a query parameter for this diagnostics-only socket.
    # In production, use HTTPS/WSS and rotate the key regularly. Local development
    # remains open so the existing dashboard works without extra configuration.
    if settings.ENV.lower() == "production":
        supplied_key = websocket.query_params.get("api_key", "")
        if not settings.ADMIN_API_KEY or not supplied_key or not secrets.compare_digest(
            supplied_key, settings.ADMIN_API_KEY
        ):
            await websocket.close(code=1008, reason="Unauthorized")
            return

    await log_manager.connect(websocket)
    try:
        await log_manager.broadcast("Client connected to live terminal.", agent="System")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_ASSETS_DIR = settings.ASSETS_DIR
os.makedirs(DATA_ASSETS_DIR, exist_ok=True)

app.mount("/assets", StaticFiles(directory=DATA_ASSETS_DIR), name="assets")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")
