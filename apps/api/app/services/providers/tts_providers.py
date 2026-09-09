import os
import logging
import subprocess
from typing import Optional
from app.services.providers.base import BaseTTSProvider

logger = logging.getLogger(__name__)

class MockTTSProvider(BaseTTSProvider):
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None
    ) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        words = len(text.split())
        duration = max(2.5, words * 0.35)

        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"anullsrc=r=44100:cl=stereo", "-t", str(duration),
            "-q:a", "9", "-acodec", "libmp3lame", output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            logger.info(f"Generated mock silent audio track ({duration:.1f}s) at {output_path}")
        except Exception:
            # Native Python WAV fallback if FFmpeg is unavailable
            import wave, struct
            wav_path = output_path if output_path.endswith(".wav") else output_path + ".wav"
            sample_rate = 22050
            num_samples = int(sample_rate * duration)
            with wave.open(wav_path, 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(struct.pack('<' + 'h' * num_samples, *[0] * num_samples))
            output_path = wav_path
            logger.info(f"Generated fallback WAV audio track at {output_path}")
            
        return output_path

class KokoroProvider(BaseTTSProvider):
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None
    ) -> str:
        # Placeholder wrapper for local Kokoro-TTS model / API
        logger.info(f"KokoroProvider synthesizing audio: '{text[:30]}...'")
        try:
            # Attempt gTTS or EdgeTTS fallback until CUDA Kokoro endpoint is linked
            import edge_tts
            communicate = edge_tts.Communicate(text, voice or "en-US-ChristopherNeural")
            await communicate.save(output_path)
            return output_path
        except Exception as e:
            logger.warning(f"Kokoro / EdgeTTS synthesis fallback to MockTTSProvider: {e}")
            mock = MockTTSProvider()
            return await mock.generate_audio(text, output_path, voice)

class PiperProvider(BaseTTSProvider):
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None
    ) -> str:
        logger.info(f"PiperProvider synthesizing text: {text[:30]}...")
        mock = MockTTSProvider()
        return await mock.generate_audio(text, output_path, voice)
