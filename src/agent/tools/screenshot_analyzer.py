from src.llm.base import BaseLLMClient
from src.vision.ocr import OCRProcessor


class ScreenshotAnalyzer:
    def __init__(self, llm: BaseLLMClient, ocr: OCRProcessor):
        self.llm = llm
        self.ocr = ocr

    async def analyze(self, image_bytes: bytes, ocr_result: str | None = None, user_input: str = "") -> str:
        if ocr_result is None:
            ocr_result = self.ocr.extract_text(image_bytes)

        prompt = (
            f"请分析以下桌面截图，用户的需求是：{user_input}\n\n"
            f"OCR识别文字：\n{ocr_result}\n\n"
            f"请重点分析：\n"
            f"1. 用户是否在截图中做了标注（如圈出、箭头指向、高亮某个区域）？如果有，标注指向的是哪个界面元素？\n"
            f"2. 被标注元素的类型（按钮、输入框、菜单项、图标等）和大致位置\n"
            f"3. 窗口标题和应用程序名称\n"
            f"4. 界面中其他可交互元素及其位置\n"
            f"5. 当前界面的状态\n\n"
            f"如果用户圈出了某个按钮，说明用户想要点击该按钮，请在分析中明确指出。"
        )

        analysis = await self.llm.generate_with_image(prompt, image_bytes)
        return analysis
