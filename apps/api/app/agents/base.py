from app.services.llm_service import LLMService

class BaseAgent:
    def __init__(self, model: str = None):
        self.llm = LLMService()
        self.model = model
        
    async def run(self, system_prompt: str, user_prompt: str, json_mode: bool = False):
        return await self.llm.generate(system_prompt, user_prompt, model=self.model, json_mode=json_mode)
