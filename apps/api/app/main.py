from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.core.config import settings
from app.api.v1 import ideas, content, research, scripts, scenes, assets, video, pipeline
from app.api import ws

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set all CORS enabled origins
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

# WebSocket route directly on app to avoid prefix routing issues
from app.core.logging import log_manager
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/api/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await log_manager.connect(websocket)
    try:
        await log_manager.broadcast("Client connected to live terminal.", agent="System")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)

# Mount static files & generated assets
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_ASSETS_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data", "assets"))
os.makedirs(DATA_ASSETS_DIR, exist_ok=True)
os.makedirs("data/assets", exist_ok=True)

if os.path.exists(DATA_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=DATA_ASSETS_DIR), name="assets")
else:
    app.mount("/assets", StaticFiles(directory="data/assets"), name="assets")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")
