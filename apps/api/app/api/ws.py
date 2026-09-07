from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.logging import log_manager

router = APIRouter()

@router.websocket("/logs")
async def websocket_logs(websocket: WebSocket):
    await log_manager.connect(websocket)
    try:
        await log_manager.broadcast("Client connected to live terminal.", agent="System")
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)
