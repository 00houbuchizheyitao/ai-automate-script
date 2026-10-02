"""实验：相邻数字在不同放大倍数下的识别率（选 scale 用，非正式测试）"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.vision.rapid_ocr import RapidOCRProcessor


def board_with_row(digits: str) -> bytes:
    """一行相邻数字，居中于 40px 格子（模拟真实扫雷数字前沿）"""
    img = Image.new("RGB", (360, 360), (222, 222, 222))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 24)
    except OSError:
        f = ImageFont.load_default()
    for i, ch in enumerate(digits):
        d.text((i * 40 + 20, 100), ch, fill=(25, 118, 210), font=f, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run(engine, png: bytes, scale: int) -> str:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    result, _ = engine(np.array(img))
    if not result:
        return "(无)"
    return "".join(r[1] for r in result)


def main():
    digits = sys.argv[1] if len(sys.argv) > 1 else "123"
    png = board_with_row(digits)
    engine = RapidOCRProcessor()._engine
    for scale in (1, 2, 3, 4):
        got = run(engine, png, scale)
        ok = "✓" if got == digits else "✗"
        print(f"scale={scale}: 期望={digits} 识别={got!r} {ok}")


if __name__ == "__main__":
    main()
