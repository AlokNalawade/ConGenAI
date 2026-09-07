from app.services.tts_service import TTSService
from app.core.logging import log_manager

class VoiceAgent:
    def __init__(self):
        self.service = TTSService()
        
    async def generate(self, text: str) -> str:
        await log_manager.broadcast(f"Synthesizing voice for text: '{text[:50]}...'", agent="VoiceAgent")
        result = await self.service.generate_voice(text)
        await log_manager.broadcast("Audio synthesis complete.", agent="VoiceAgent")
        return result
