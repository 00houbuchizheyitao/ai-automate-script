from src.agent.prompts.script_generation import (
    SCRIPT_GENERATION_PROMPT,
    SCRIPT_GENERATION_TEXT_ONLY_PROMPT,
)
from src.llm.base import BaseLLMClient


class ScriptGeneratorTool:
    def __init__(self, llm: BaseLLMClient):
        self.llm = llm

    async def generate(self, user_requirement: str, analysis: str = "", ocr_text: str = "") -> str:
        if analysis or ocr_text:
            prompt = SCRIPT_GENERATION_PROMPT.format(
                analysis=analysis or "无截图分析结果",
                user_requirement=user_requirement,
                ocr_text=ocr_text or "无OCR识别结果",
            )
        else:
            prompt = SCRIPT_GENERATION_TEXT_ONLY_PROMPT.format(
                user_requirement=user_requirement,
            )

        script = await self.llm.generate(prompt)
        return self._extract_code(script)

    async def refine(self, original_script: str, issues: str, analysis: str = "") -> str:
        from src.agent.prompts.script_generation import SCRIPT_REFINEMENT_PROMPT

        prompt = SCRIPT_REFINEMENT_PROMPT.format(
            original_script=original_script,
            issues=issues,
            analysis=analysis or "无截图分析结果",
        )

        script = await self.llm.generate(prompt)
        return self._extract_code(script)

    @staticmethod
    def _extract_code(response: str) -> str:
        if "```python" in response:
            start = response.index("```python") + len("```python")
            end = response.index("```", start)
            return response[start:end].strip()
        if "```" in response:
            start = response.index("```") + len("```")
            end = response.index("```", start)
            return response[start:end].strip()
        return response.strip()
