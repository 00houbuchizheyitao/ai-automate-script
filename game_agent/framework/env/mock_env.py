"""合成游戏环境：闭环自测/CI 用的零依赖"游戏"。

规则：画面上有一个白色方块（靶子），点击落在靶子范围内即成功。
- 不依赖任何真实游戏，可在 CI/无显示器环境跑通全循环
- 支持固定随机种子 → 同一考题可复现（benchmark 复现性要求）
- 每次点击在画面上留下红点标记 → 多模态 LLM 能看到自己的操作反馈
"""
from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw

from game_agent.framework.env.base import Environment
from game_agent.framework.types import Action, FrameAnalysis, Status, Task

WIDTH, HEIGHT = 800, 600
TARGET_SIZE = 48          # 靶子边长
HIT_HALF = 34             # 命中判定半径（略大于方块，照顾 LLM 的瞄准误差）


class MockEnv(Environment):
    def __init__(self, seed: int | None = 42):
        self._seed = seed
        self._rng = random.Random(seed)
        self._pinned: tuple[int, int] | None = None
        self.target = self._new_target()
        self._last_click: tuple[int, int] | None = None
        self._click_history: list[tuple[int, int]] = []
        self._steps = 0

    # ---------- Environment 契约 ----------

    @property
    def screen_size(self) -> tuple[int, int]:
        return (WIDTH, HEIGHT)

    def capture(self) -> FrameAnalysis:
        img = Image.new("RGB", (WIDTH, HEIGHT), (30, 32, 38))
        draw = ImageDraw.Draw(img)

        tx, ty = self.target
        draw.rectangle(
            [tx - TARGET_SIZE // 2, ty - TARGET_SIZE // 2,
             tx + TARGET_SIZE // 2, ty + TARGET_SIZE // 2],
            fill=(245, 245, 245),
        )
        # 上次点击的红点反馈（LLM 能看到自己打哪了）
        for cx, cy in self._click_history[-3:]:
            draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(220, 60, 60))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        notes = ""
        if self._click_history:
            dots = min(len(self._click_history), 3)
            notes = (f"画面中的 {dots} 个红点是你此前点击的落点（不是目标），"
                     f"白色方块才是目标。")
        return FrameAnalysis(screenshot=buf.getvalue(), notes=notes)

    def act(self, action: Action) -> None:
        self._steps += 1
        if action.type == "click" and action.x is not None and action.y is not None:
            self._last_click = (action.x, action.y)
            self._click_history.append(self._last_click)
        # key/move/wait 对本合成游戏无状态影响

    def check(self, task: Task) -> Status:
        if self._last_click is not None:
            tx, ty = self.target
            cx, cy = self._last_click
            if abs(cx - tx) <= HIT_HALF and abs(cy - ty) <= HIT_HALF:
                return Status.SUCCESS
        if self._steps >= task.timeout_steps:
            return Status.FAIL
        return Status.RUNNING

    def reset(self) -> None:
        self._rng = random.Random(self._seed)
        self.target = self._pinned if self._pinned is not None else self._new_target()
        self._last_click = None
        self._click_history.clear()
        self._steps = 0

    # ---------- 测试钩子 ----------

    def _new_target(self) -> tuple[int, int]:
        margin = TARGET_SIZE
        return (
            self._rng.randint(margin, WIDTH - margin),
            self._rng.randint(margin, HEIGHT - margin),
        )

    def set_target(self, x: int, y: int) -> None:
        """测试钩子：固定靶位（跨 reset 存活），让脚本化决策器可精确命中。"""
        self._pinned = (x, y)
        self.target = (x, y)
