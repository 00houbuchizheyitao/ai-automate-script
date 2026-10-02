"""RapidOCR 后端：与 OCRProcessor 同接口，模型随 pip 包分发，运行时零网络依赖。

背景：easyocr 模型托管在 GitHub Releases，国内网络下载易反复失败
（缓存目录只剩 0 字节 temp.zip）。RapidOCR 的 onnx 模型打包在 wheel 内，
pip 安装即可用。输出格式与 OCRProcessor.extract_text_with_positions 一致。
"""
from __future__ import annotations

import io

import numpy as np


class RapidOCRProcessor:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def extract_text_with_positions(self, image_bytes: bytes) -> list[dict]:
        from PIL import Image

        image = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        result, _ = self._engine(image)
        extracted: list[dict] = []
        if not result:
            return extracted
        for box, text, score in result:
            if score < 0.3:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            extracted.append({
                "text": text,
                "confidence": float(score),
                "position": {
                    "x": int(sum(xs) / len(xs)),
                    "y": int(sum(ys) / len(ys)),
                    "bbox": [[int(px), int(py)] for px, py in box],
                },
            })
        return extracted

    def extract_text(self, image_bytes: bytes) -> str:
        return "\n".join(item["text"] for item in self.extract_text_with_positions(image_bytes))
