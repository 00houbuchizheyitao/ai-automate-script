import re
from src.agent.prompts.script_generation import SCRIPT_GENERATION_PROMPT
from src.llm.base import BaseLLMClient


class ScriptGenerator:
    def __init__(self, llm: BaseLLMClient):
        self.llm = llm

    async def generate_script(self, user_requirement: str, analysis: str = "", ocr_text: str = "") -> str:
        prompt = SCRIPT_GENERATION_PROMPT.format(
            analysis=analysis or "无截图分析结果",
            user_requirement=user_requirement,
            ocr_text=ocr_text or "无OCR识别结果",
        )
        response = await self.llm.generate(prompt)
        return self._extract_code(response)

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

    @staticmethod
    def inject_safety(script: str) -> str:
        safety_header = '''import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

SAFETY_CONFIRMED = False

def confirm_execution():
    """安全确认：脚本执行前需用户确认"""
    global SAFETY_CONFIRMED
    response = input("确认执行此自动化脚本？(yes/no): ")
    if response.lower() != "yes":
        logger.info("用户取消执行")
        sys.exit(0)
    SAFETY_CONFIRMED = True

confirm_execution()
'''
        if "confirm_execution" not in script:
            script = safety_header + "\n" + script
        return script
