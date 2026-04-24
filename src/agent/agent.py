from src.agent.prompts.system_prompt import SYSTEM_PROMPT
from src.agent.tools.screenshot_analyzer import ScreenshotAnalyzer
from src.agent.tools.script_generator import ScriptGeneratorTool
from src.config.settings import AppSettings
from src.llm.ollama_client import OllamaClient
from src.script.executor import ScriptSaver
from src.vision.ocr import OCRProcessor


class Agent:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.llm = OllamaClient(settings)
        self.ocr = OCRProcessor()
        self.screenshot_analyzer = ScreenshotAnalyzer(self.llm, self.ocr)
        self.script_generator = ScriptGeneratorTool(self.llm)
        self.script_saver = ScriptSaver(settings.scripts_output_dir)
        self.conversation_history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._pending_image: bytes | None = None

    def set_pending_image(self, image_bytes: bytes):
        self._pending_image = image_bytes

    async def process(self, user_input: str) -> str:
        if self._pending_image:
            return await self._process_with_image(user_input)

        # 添加用户输入到历史记录
        self.conversation_history.append({"role": "user", "content": user_input})

        # 直接调用 LLM，让其决定是回复还是生成脚本
        response = await self.llm.generate(user_input, self.conversation_history[:-1])

        self.conversation_history.append({"role": "assistant", "content": response})

        # 检查是否生成了代码块
        script = self._extract_code(response)
        
        # 启发式判断：只有当代码块包含相关自动化库，且用户意图似乎是生成脚本时才保存
        automation_libraries = ["pyautogui", "cv2", "keyboard", "mss"]
        if script and any(lib in script for lib in automation_libraries):
            # 如果回复中除了代码块还有很多文字，可能只是在解释代码，也保存
            filepath = self.script_saver.save(script)
            return f"{response}\n\n---\n**脚本已生成并保存至：** {filepath}"

        return response

    async def _process_with_image(self, user_input: str) -> str:
        image_bytes = self._pending_image
        self._pending_image = None

        # 1. OCR 提取文字
        ocr_result = self.ocr.extract_text(image_bytes)
        
        # 2. 视觉分析（分析截图内容和用户标注）
        analysis = await self.screenshot_analyzer.analyze(image_bytes, ocr_result, user_input)

        # 3. 构造复合输入
        combined_input = (
            f"用户提供了一张截图。\n"
            f"视觉分析结果：\n{analysis}\n\n"
            f"OCR 识别文字：\n{ocr_result}\n\n"
            f"用户补充需求：{user_input if user_input else '无'}"
        )
        
        self.conversation_history.append({"role": "user", "content": combined_input})

        # 4. 让 LLM 决定回复内容（是对话还是生成脚本）
        response = await self.llm.generate(combined_input, self.conversation_history[:-1])
        self.conversation_history.append({"role": "assistant", "content": response})

        # 5. 检查是否包含代码块
        script = self._extract_code(response)
        automation_libraries = ["pyautogui", "cv2", "keyboard", "mss"]
        if script and any(lib in script for lib in automation_libraries):
            filepath = self.script_saver.save(script)
            return f"{response}\n\n---\n**脚本已生成并保存至：** {filepath}"

        return response

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
        return ""

    def clear_history(self):
        self.conversation_history = []
        self._pending_image = None
