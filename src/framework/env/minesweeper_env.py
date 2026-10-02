"""扫雷环境适配器：框架接入第一个真实窗口游戏。

游戏本体：仓库根目录 minesweeper.py（pygame，9×9 / 10 雷，40px 格子，
窗口标题 "扫雷  seed=..."，结算时画面中央渲染大号 WIN / LOSE）。

适配者只需实现 check/reset——capture/act/screen_size 全部继承 WindowEnv，
验证"桌面游戏通用层"的设计承诺。

坐标约定：
- LLM 视角：region 内图像坐标（与 WindowEnv 一致）
- 游戏棋盘：COLS×ROWS 格子，每格 CELL 像素，棋盘铺满整个窗口
- board_cell(): 图像坐标 → (col, row)，供 check 内部换算用
"""
from __future__ import annotations

import time

from src.framework.env.window_env import WindowEnv
from src.framework.types import Action, Status, Task

COLS, ROWS, CELL = 9, 9, 40
BOARD = (COLS * CELL, ROWS * CELL)  # (360, 360)


class MinesweeperEnv(WindowEnv):
    """扫雷适配器。

    参数:
        window_title: 窗口标题子串，默认 "扫雷"（跟随窗口移动）
        settle_s: 动作后等待游戏渲染的时长（连锁翻格需要一点时间）
    任务约定（Task.meta）:
        safe_opens: 需安全翻开的格子数（默认 3）
    """

    def __init__(self, window_title: str = "扫雷",
                 settle_s: float = 0.35, **kwargs):
        kwargs.setdefault("region", (0, 0, *BOARD))
        super().__init__(window_title=window_title, **kwargs)
        self.settle_s = settle_s

    # ---------- 坐标换算 ----------

    @staticmethod
    def board_cell(x: int, y: int) -> tuple[int, int]:
        """图像坐标 → 棋盘 (col, row)；越界返回 (-1, -1)。"""
        if not (0 <= x < BOARD[0] and 0 <= y < BOARD[1]):
            return (-1, -1)
        return (x // CELL, y // CELL)

    # ---------- Environment 契约 ----------

    def act(self, action: Action) -> None:
        super().act(action)
        time.sleep(self.settle_s)  # 连锁翻格/结算画面需要渲染时间

    def check(self, task: Task) -> Status:
        """判定：OCR 找大号 WIN/LOSE 结算字样，否则数已翻安全格。"""
        frame = self.capture()
        texts = [e.text.strip().upper() for e in frame.elements]

        if any("LOSE" in t for t in texts):
            return Status.FAIL
        if any("WIN" in t for t in texts):
            return Status.SUCCESS

        # 无结算画面：统计已翻开的安全格数（数字格 + 空白格都是安全翻开）
        need = int(task.meta.get("safe_opens", 3))
        if self._opened_cells(frame) >= need:
            return Status.SUCCESS
        return Status.RUNNING

    def reset(self) -> None:
        """重开一局：结算画面按 R 键；无结算画面时 R 也直接开新局。"""
        self.act(Action(type="key", key="r"))
        time.sleep(self.settle_s)


    # ---------- 内容校验：以游戏实际画面为参照物 ----------

    BOARD_GRAYS = ((100, 100, 100),   # 未翻开格
                   (144, 144, 144),   # 背景
                   (222, 222, 222))   # 已翻开格

    def _content_score(self, png: bytes) -> float:
        """颜色签名评分：中央区域落在棋盘三种灰色的像素占比。

        扫雷窗口画面几乎 100% 由这三种灰构成；对话/IDE/网页等标题恰含
        "扫雷"的干扰窗口是白底彩字或深底，得分接近 0。颜色直方图对窗口
        缩放不敏感，比模板匹配更稳。
        """
        import io

        import numpy as np
        from PIL import Image

        img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.int16)
        h, w, _ = img.shape
        if h < 100 or w < 100:
            return 0.0
        center = img[h // 4: 3 * h // 4, w // 4: 3 * w // 4].reshape(-1, 3)
        close = sum(int((np.abs(center - np.array(g)).sum(axis=1) <= 24).sum())
                    for g in self.BOARD_GRAYS)
        return close / len(center)

    # ---------- 内部 ----------

    @staticmethod
    def _opened_cells(frame) -> int:
        """估算已翻开格数：OCR 到的数字格各占一格（粗估，够判定用）。

        连锁翻开的空白格没有数字，OCR 读不到——所以这个计数偏保守。
        判定策略：数字格数 ≥ need 即视为达标（空白格只会更多）。
        标题栏区域（含 "seed=42" 字样）被排除，防止误计。
        """
        seen: set[tuple[int, int]] = set()
        for e in frame.elements:
            text = e.text.strip()
            if e.y < 40:  # 标题栏区（外框定位时约39px高），排除 seed=42 误读
                continue
            if text.isdigit() and 1 <= int(text) <= 8:
                cell = MinesweeperEnv.board_cell(e.x, e.y)
                if cell != (-1, -1):
                    seen.add(cell)
        return len(seen)
