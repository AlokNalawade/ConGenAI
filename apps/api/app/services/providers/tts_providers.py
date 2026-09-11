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
        import shutil, imageio_ffmpeg
        ffmpeg_bin = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

        # Try native macOS 'say' command for realistic spoken narration audio
        if shutil.which("say") and text and text.strip():
            try:
                aiff_tmp = output_path + f"_{os.urandom(4).hex()}.aiff"
                subprocess.run(["say", "-o", aiff_tmp, text], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                cmd = [
                    ffmpeg_bin, "-y", "-i", aiff_tmp,
                    "-acodec", "libmp3lame", "-q:a", "2", output_path
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if os.path.exists(aiff_tmp):
                    os.remove(aiff_tmp)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                    logger.info(f"Generated spoken audio track via macOS say at {output_path}")
                    return output_path
            except Exception as e:
                logger.warning(f"Native macOS say TTS generation failed: {e}")

        # Fallback to anullsrc silent audio track if say is unavailable or fails
        words = len(text.split()) if text else 1
        duration = max(2.5, words * 0.35)

        cmd = [
            ffmpeg_bin, "-y", "-f", "lavfi", "-i",
            f"anullsrc=r=44100:cl=stereo", "-t", str(duration),
            "-q:a", "9", "-acodec", "libmp3lame", output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            logger.info(f"Generated mock silent audio track ({duration:.1f}s) at {output_path}")
        except Exception:
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
