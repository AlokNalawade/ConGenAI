from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        pass

class BaseImageProvider(ABC):
    @abstractmethod
    async def generate_image(
        self,
        prompt: str,
        width: int = 1080,
        height: int = 1920,
        output_path: Optional[str] = None
    ) -> str:
        pass

class BaseTTSProvider(ABC):
    @abstractmethod
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None
    ) -> str:
        pass

class BaseVideoProvider(ABC):
    @abstractmethod
    async def render_video(
        self,
        scenes: list,
        output_path: str,
        audio_path: Optional[str] = None
    ) -> str:
        pass
