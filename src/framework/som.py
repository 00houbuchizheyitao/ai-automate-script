"""SoM（Set-of-Mark）标注工具：把编号徽章画到截图上，供 LLM 以编号指代元素。

经典 SoM（microsoft/SoM）依赖检测模型寻找元素；本框架的 SoM 由
Environment 自行声明元素位置（确定性几何或未来的检测模型皆可作为
来源），这里只负责两件事：
1. 在截图副本上绘制编号徽章（避开元素主体，防止遮挡关键信息）
2. 输出 编号→点击目标点（图像坐标） 的映射，由 Runner 解析 LLM 引用

注意：徽章绘制位置 ≠ 点击目标点。例如扫雷把徽章画在格子左上角，
但点击目标点是格子中心（那里才是"安全落点"）。
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

BADGE_COLOR = (233, 30, 99)   # 品红——与游戏内颜色（灰板/蓝绿红数字）明显区分
TEXT_COLOR = (255, 255, 255)
BADGE_RADIUS = 11


@dataclass(frozen=True)
class SomTag:
    id: str
    x: int  # 点击目标点（图像坐标）——注意≠徽章绘制位置
    y: int


def _load_font(size: int):
    for name in ("consolab.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def draw_som_tags(screenshot: bytes, tags: list[SomTag]) -> bytes:
    """在截图副本上绘制编号徽章，返回标注图 PNG 字节（原图不变）。"""
    img = Image.open(io.BytesIO(screenshot)).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = _load_font(13)
    for t in tags:
        bx, by = t.x - 20, t.y - 20  # 徽章在目标点左上偏移处，避开元素主体
        draw.ellipse([bx - BADGE_RADIUS, by - BADGE_RADIUS,
                      bx + BADGE_RADIUS, by + BADGE_RADIUS], fill=BADGE_COLOR)
        draw.text((bx, by), t.id, fill=TEXT_COLOR, font=font, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
