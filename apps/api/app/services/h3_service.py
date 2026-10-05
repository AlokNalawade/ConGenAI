import asyncio
import os
import shlex
import shutil
import uuid
from pathlib import Path

from app.core.config import settings


class H3MacService:
    """Run MiniMax H3 through the external 16 GB Apple-Silicon MLX runner.

    The runner command is deliberately explicit and argument-based; prompts are
    never passed through a shell. This keeps ConGenAI independent of the H3
    implementation while allowing the Mac runner to evolve.
    """

    def __init__(self):
        self.command = os.getenv("H3_COMMAND", "h3stream")
        self.model_dir = os.getenv("H3_MODEL_DIR", "models")
        self.output_dir = Path(settings.ASSETS_DIR) / "videos" / "h3"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _executable(self) -> str:
        path = shutil.which(self.command)
        if not path:
            raise RuntimeError(
                f"H3 runner '{self.command}' not found. "
                "Install minimax-h3-stream-mac and ensure h3stream is on PATH."
            )
        return path

    async def generate(
        self,
        prompt: str,
        width: int = 640,
        height: int = 384,
        seconds: float = 5.0,
        steps: int = 16,
        seed: int = 21,
        audio: bool = True,
    ) -> str:
        if not prompt.strip():
            raise ValueError("H3 prompt must not be empty")
        if width % 32 or height % 32:
            raise ValueError("H3 width and height must be multiples of 32")
        if width > 640 or height > 640:
            raise ValueError("Mac 16 GB smoke-test mode is capped at 640px per side")
        if not 1 <= seconds <= 5:
            raise ValueError("Mac smoke-test duration must be between 1 and 5 seconds")
        if not 4 <= steps <= 16:
            raise ValueError("Mac smoke-test steps must be between 4 and 16")

        output = self.output_dir / f"h3_{uuid.uuid4().hex}.mp4"
        run_dir = self.output_dir / f"run_{uuid.uuid4().hex}"
        run_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self._executable(),
            "generate",
            "--model-dir", self.model_dir,
            "--run-dir", str(run_dir),
            "--output", str(output),
            "--prompt", prompt,
            "--width", str(width),
            "--height", str(height),
            "--seconds", str(seconds),
            "--steps", str(steps),
            "--seed", str(seed),
            "--memory-limit-gib", os.getenv("H3_MEMORY_LIMIT_GIB", "12.5"),
            "--i-understand-experimental",
        ]
        if audio:
            cmd.append("--audio")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace")[-6000:]
            raise RuntimeError(f"H3 generation failed (exit {proc.returncode}): {detail}")

        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("H3 runner completed without producing an MP4")

        return str(output)
