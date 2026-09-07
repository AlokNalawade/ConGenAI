import os
import uuid
import asyncio
import edge_tts
from gtts import gTTS

class TTSService:
    def __init__(self):
        self.output_dir = os.path.join("data", "assets", "audio")
        os.makedirs(self.output_dir, exist_ok=True)
        self.default_voice = "en-US-ChristopherNeural"

    async def generate_voice(self, text: str, voice: str = None) -> str:
        v = voice or self.default_voice
        filename = f"{uuid.uuid4()}.mp3"
        filepath = os.path.join(self.output_dir, filename)
        
        # Primary: edge-tts
        try:
            communicate = edge_tts.Communicate(text, v)
            await communicate.save(filepath)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 500:
                print(f"Edge-TTS synthesis success: {filepath} ({os.path.getsize(filepath)} bytes)")
                return filepath
        except Exception as e:
            print(f"Edge-TTS synthesis notice ({e}), trying gTTS fallback...")

        # Fallback: gTTS
        try:
            def _gtts_gen():
                tts = gTTS(text=text, lang='en')
                tts.save(filepath)
            await asyncio.to_thread(_gtts_gen)
            print(f"gTTS fallback synthesis success: {filepath} ({os.path.getsize(filepath)} bytes)")
            return filepath
        except Exception as e:
            print(f"gTTS fallback error: {e}")
            raise RuntimeError(f"Failed to generate voice audio: {str(e)}")
