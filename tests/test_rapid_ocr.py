"""RapidOCR 后端测试：合成数字图验证识别与坐标（不依赖网络/游戏窗口）。"""
import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from game_agent.vision.rapid_ocr import RapidOCRProcessor


def _digit_image() -> bytes:
    """棋盘风格合成图：浅灰底 + 24px 粗体数字居中于 40px 格子（同扫雷渲染）"""
    img = Image.new("RGB", (360, 360), (222, 222, 222))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 24)
    except OSError:
        pytest.skip("测试字体不可用（不影响生产）")
    # 数字居中于格子中心，与 minesweeper.py 的 blit(center=rect.center) 一致
    for text, cx, cy, color in (("2", 20, 20, (25, 118, 210)),
                                ("3", 60, 60, (211, 47, 47))):
        d.text((cx, cy), text, fill=color, font=f, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def ocr():
    try:
        return RapidOCRProcessor()
    except ImportError:
        pytest.skip("rapidocr_onnxruntime 未安装")


def test_reads_digits_with_positions(ocr):
    items = ocr.extract_text_with_positions(_digit_image())
    texts = [i["text"] for i in items]
    assert any("2" in t for t in texts), f"未识别到 2: {texts}"
    assert any("3" in t for t in texts), f"未识别到 3: {texts}"
    for i in items:
        assert 0 <= i["position"]["x"] < 360
        assert 0 <= i["position"]["y"] < 360
        assert i["confidence"] > 0.3


def test_blank_board_returns_empty(ocr):
    img = Image.new("RGB", (360, 360), (222, 222, 222))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert ocr.extract_text_with_positions(buf.getvalue()) == []
