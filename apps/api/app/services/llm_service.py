import json
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.logging import log_manager


class LLMService:
    def __init__(self):
        # Default to local Ollama/OpenAI-compatible inference.
        self.client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
        )
        self.default_model = settings.DEFAULT_MODEL or settings.LLM_DEFAULT_MODEL

    async def _resolve_model(self, model: str) -> str:
        target = model or self.default_model
        try:
            models_page = await self.client.models.list()
            available = [m.id for m in models_page.data]
            if not available:
                return target
            if target in available:
                return target
            for m in available:
                if "llama3" in m.lower():
                    return m
            for m in available:
                if "llama" in m.lower():
                    return m
            return available[0]
        except Exception:
            return target

    async def get_available_models(self) -> list[str]:
        try:
            models_page = await self.client.models.list()
            models = [m.id for m in models_page.data]
            if models:
                return models
        except Exception as e:
            print(f"Error fetching models list: {e}")
        return ["llama3:latest", "llama3.1", "mistral", "gemma2", "phi3", "deepseek-r1"]

    async def generate(self, system_prompt: str, user_prompt: str, model: str = None, json_mode: bool = False):
        requested_model = model or self.default_model
        model_to_use = await self._resolve_model(requested_model)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Do not expose full prompts through an unauthenticated log stream.
        # Keep operational metadata only; detailed prompt logging belongs in an
        # authenticated/admin diagnostics path.
        await log_manager.broadcast(
            f"🦙 [LLM REQUEST] model={model_to_use}",
            agent="LLMService",
        )

        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self.client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                **kwargs,
            )
            content = response.choices[0].message.content

            await log_manager.broadcast(
                f"🦙 [LLM RESPONSE] model={model_to_use} chars={len(content or '')}",
                agent="LLMService",
            )

            if json_mode:
                return json.loads(content)
            return content
        except Exception as e:
            # Keep provider errors out of the websocket payload by default.
            enable_mock = settings.ALLOW_QA_FALLBACK
            if not enable_mock:
                raise RuntimeError(
                    f"LLM generation failed for model {model_to_use}"
                ) from e

            mock_res = self._get_mock_response(system_prompt, json_mode)
            mock_str = json.dumps(mock_res, indent=2) if isinstance(mock_res, dict) else str(mock_res)
            await log_manager.broadcast(
                f"⚠️ LLM request failed; using QA fallback output ({len(mock_str)} chars)",
                agent="LLMService",
            )
            return mock_res

    def _get_mock_response(self, system_prompt: str, json_mode: bool):
        if not json_mode:
            return "This is a mocked response because the LLM failed."

        if "Research" in system_prompt:
            return {
                "summary": "Mocked research summary.",
                "key_points": ["Point 1", "Point 2"],
                "hooks": ["Did you know..."],
            }
        if "Scriptwriter" in system_prompt:
            return {
                "hook": "Mock hook",
                "body": "Mock body text",
                "cta": "Like and subscribe!",
                "estimated_duration": 30,
                "word_count": 50,
            }
        if "Director" in system_prompt or "Scene" in system_prompt:
            return {
                "scenes": [
                    {
                        "scene_number": 1,
                        "duration": 5.0,
                        "narration": "This is scene 1",
                        "visual_description": "A beautiful landscape",
                        "visual_prompt": "Beautiful landscape, 4k",
                    }
                ]
            }
        return {}
