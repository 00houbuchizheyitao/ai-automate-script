"""感知器：把一帧画面变成 FrameAnalysis（结构化情报层）。

v0：复用现有 OCRProcessor（easyocr，带坐标），懒加载避免拖累测试。
v1 扩展点：模板匹配 UI 元素、血条比例检测等。
"""
from __future__ import annotations

from src.framework.types import Element, FrameAnalysis


class Perception:
    def __init__(self, use_ocr: bool = True, ocr_languages: list[str] | None = None):
        self.use_ocr = use_ocr
        self._ocr_languages = ocr_languages
        self._ocr = None  # 懒加载：easyocr 首次初始化很重

    def _get_ocr(self):
        if self._ocr is None:
            # 优先 RapidOCR（模型随 pip 包分发，无网络依赖）；
            # 未安装则回退 easyocr（首次初始化需从 GitHub 下载模型）。
            try:
                from src.vision.rapid_ocr import RapidOCRProcessor

                self._ocr = RapidOCRProcessor()
            except ImportError:
                from src.vision.ocr import OCRProcessor

                self._ocr = OCRProcessor(languages=self._ocr_languages)
        return self._ocr

    def analyze(self, screenshot: bytes, ocr_enabled: bool | None = None) -> FrameAnalysis:
        use_ocr = self.use_ocr if ocr_enabled is None else ocr_enabled
        elements: list[Element] = []

        if use_ocr:
            try:
                for item in self._get_ocr().extract_text_with_positions(screenshot):
                    pos = item["position"]
                    elements.append(
                        Element(
                            text=item["text"],
                            x=pos["x"],
                            y=pos["y"],
                            confidence=item["confidence"],
                        )
                    )
            except Exception as e:  # 感知失败不应打断循环，降级为纯图像通道
                return FrameAnalysis(screenshot=screenshot, notes=f"(OCR 异常: {e})")

        return FrameAnalysis(screenshot=screenshot, elements=tuple(elements))
