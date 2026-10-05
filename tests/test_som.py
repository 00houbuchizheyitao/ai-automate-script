"""SoM 与编号解析测试：绘制、Runner 符号解析、扫雷格子分类。"""
import asyncio
import io
import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from src.framework import Action, ActionParseError, AgentRunner, MockEnv, Status, Task
from src.framework.env.minesweeper_env import MinesweeperEnv
from src.framework.som import SomTag, draw_som_tags


def test_draw_som_tags_produces_annotated_copy():
    """标注图与原图同尺寸但内容不同（有品红徽章）"""
    img = Image.new("RGB", (100, 100), (222, 222, 222))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    original = buf.getvalue()

    annotated = draw_som_tags(original, [SomTag(id="1", x=50, y=50)])
    out = Image.open(io.BytesIO(annotated))
    assert out.size == (100, 100)
    assert annotated != original
    # 徽章中心应为品红系颜色（badge 画在目标点左上偏移处）
    arr = np.asarray(out)
    badge_zone = arr[50 - 20 - 5: 50 - 20 + 5, 50 - 20 - 5: 50 - 20 + 5]
    assert badge_zone.reshape(-1, 3).mean(axis=0)[0] > 150  # R 通道显著


class _TaggedMock(MockEnv):
    """MockEnv + 本帧 SoM 标注：验证 Runner 的编号→坐标解析"""

    def capture(self):
        frame = super().capture()
        return type(frame)(screenshot=frame.screenshot,
                           elements=frame.elements, notes=frame.notes,
                           tags={"5": (100, 100), "9": (200, 200)})


def test_runner_resolves_id_to_coordinates():
    """LLM 引用编号 → Runner 解析为坐标 → env.act 收到正确落点"""
    env = _TaggedMock(seed=1)
    env.set_target(100, 100)  # 编号 5 的点击目标点恰是靶心
    received: list[Action] = []

    async def decider(prompt: str, images: list[bytes]) -> str:
        assert len(images) == 1
        return json.dumps({"type": "click", "id": "5"})

    runner = AgentRunner(env=env, decider=decider, step_interval_s=0)

    orig_act = env.act

    def spy_act(a):
        received.append(a)
        orig_act(a)

    env.act = spy_act
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))

    assert result.status is Status.SUCCESS
    assert received[0].x == 100 and received[0].y == 100
    assert received[0].id == "5"


def test_runner_rejects_unknown_tag_id():
    """引用不存在/已翻开的编号 → 解析错误反馈（含可用编号）后仍失败则报错"""
    env = _TaggedMock(seed=1)
    env.set_target(100, 100)

    async def decider(prompt: str, images: list[bytes]) -> str:
        return json.dumps({"type": "click", "id": "77"})  # 不在标注图中

    runner = AgentRunner(env=env, decider=decider, step_interval_s=0, parse_retries=1)
    with pytest.raises(ActionParseError, match="编号 '77' 不在当前标注图"):
        asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))


def _board_image(revealed: set[tuple[int, int]]) -> bytes:
    """合成扫雷棋盘：深灰未翻开格 + 指定坐标的浅色已翻开格（含边框偏移）"""
    from src.framework.env.minesweeper_env import DEFAULT_BOARD_ORIGIN, CELL, COLS, ROWS
    ox, oy = DEFAULT_BOARD_ORIGIN
    img = Image.new("RGB", (ox + 9 * CELL + 8, oy + 9 * CELL + 9), (144, 144, 144))
    d = ImageDraw.Draw(img)
    for row in range(ROWS):
        for col in range(COLS):
            x0, y0 = ox + col * CELL, oy + row * CELL
            light = (col, row) in revealed
            d.rectangle([x0, y0, x0 + CELL - 1, y0 + CELL - 1],
                        fill=(222, 222, 222) if light else (100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_minesweeper_som_classification():
    """格子亮度分类：浅色格不打标记，深灰格打标记且编号按几何位置固定"""
    revealed = {(2, 2), (3, 3)}
    tags, annotated = MinesweeperEnv._som(_board_image(revealed))
    id_of = lambda c, r: str(r * 9 + c + 1)

    assert id_of(2, 2) not in tags          # 已翻开 → 无标记
    assert id_of(3, 3) not in tags
    assert id_of(0, 0) in tags              # 未翻开 → 有标记
    assert id_of(8, 8) in tags
    assert len(tags) == 81 - len(revealed)
    # 点击目标点 = 格子中心（图像坐标，含外框偏移）
    from src.framework.env.minesweeper_env import DEFAULT_BOARD_ORIGIN
    ox, oy = DEFAULT_BOARD_ORIGIN
    assert tags[id_of(0, 0)] == (ox + 20, oy + 20)
    assert annotated[:4] == b"\x89PNG"
