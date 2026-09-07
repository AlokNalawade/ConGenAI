from typing import List
from fastapi import WebSocket
from datetime import datetime

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
        import json
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] [{agent}] {message}"
        print(formatted_message)
        
        payload = json.dumps({"agent": agent, "message": message, "time": timestamp})
        
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect(connection)

log_manager = LogManager()
