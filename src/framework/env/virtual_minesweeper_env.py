"""无头扫雷环境：SDL dummy 渲染 + 进程内事件注入。

用途：基准测试零桌面干扰——没有真实窗口、不碰鼠标键盘，跑测试期间
可以正常使用电脑；且支持多实例并行跑分、可在 CI 中运行。

与真实窗口环境（MinesweeperEnv）的关系：
- 游戏逻辑与渲染管线完全一致（同一个 MinesweeperApp/draw）
- Agent 依然只看渲染像素、只发逻辑点击——基准有效性不变
- 仅"事件运输方式"不同：进程内事件注入 vs OS 鼠标消息；
  后者已由真实窗口闭环单独验证
- 差异点：无头画面是纯棋盘（360×360，无标题栏/边框），
  棋盘原点 = (0, 0)，也没有标题栏过滤的需要
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from src.framework.env.minesweeper_env import BOARD, MinesweeperEnv
from src.framework.types import Action, FrameAnalysis, Status, Task

_ROOT = Path(__file__).resolve().parents[3]


class VirtualMinesweeperEnv(MinesweeperEnv):
    """无头扫雷：继承判定/SoM/计数逻辑，替换渲染与事件运输层。

    注意：不调用 MinesweeperEnv/WindowEnv 的 __init__（绕开真实窗口
    依赖 mss/pyautogui/pygetwindow），所需实例属性自行初始化。
    """

    def __init__(self, seed: int | None = 42, use_ocr: bool = True,
                 settle_s: float = 0.0):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        try:
            from minesweeper import MinesweeperApp
        except ImportError:
            sys.path.insert(0, str(_ROOT))
            from minesweeper import MinesweeperApp

        self._seed = seed
        self.settle_s = settle_s
        self.board_origin = (0, 0)   # 无头画面 = 纯棋盘，无外框偏移
        self._title_bar_h = 0        # 无标题栏 → 已翻格计数不做标题栏过滤
        self._flagged: set[str] = set()
        from src.framework.perception import Perception
        self._perception = Perception(use_ocr=use_ocr)
        self._app = MinesweeperApp(seed=seed, headless=True)

    # ---------- Environment 契约 ----------

    @property
    def screen_size(self) -> tuple[int, int]:
        return BOARD

    def capture(self) -> FrameAnalysis:
        self._app.render()
        import io

        import pygame as pg
        to_bytes = getattr(pg.image, "tobytes", pg.image.tostring)
        raw = to_bytes(self._app.screen, "RGB")
        from PIL import Image
        png = self._rgb_to_png(Image.frombytes("RGB", self._app.screen.get_size(), raw))
        frame = self._perception.analyze(png)
        opened, tags, annotated = self._som(png, origin=self.board_origin,
                                            flagged=self._flagged)
        note = ("棋盘为 9×9 格子铺满整个窗口（每格 40 像素）。"
                "深灰色格子 = 未翻开（可以点击）；"
                "浅色格子 = 已翻开（上面可能显示数字），不可再点。"
                "第二张图是 SoM 编号标注图，点击深灰格子直接引用其编号。")
        return FrameAnalysis(screenshot=png, elements=frame.elements,
                             notes=note, annotated=annotated, tags=tags,
                             opened_ids=frozenset(opened))

    def act(self, action: Action) -> None:
        """把逻辑动作注入游戏事件循环（与真实鼠标事件走同一处理路径）。"""
        import pygame as pg

        if action.type == "flag":
            for tid in action.ids or ([action.id] if action.id else []):
                self._flagged.add(tid)   # 标记仅驱动 SoM 橙三角，无头环境无旗子
            return
        if action.type == "click" and action.x is not None and action.y is not None:
            pos = (int(action.x), int(action.y))
            self._app.handle_event(
                pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=pos))
            self._app.handle_event(
                pg.event.Event(pg.MOUSEBUTTONUP, button=1, pos=pos))
        elif action.type == "key" and action.key:
            key = getattr(pg, f"K_{action.key.lower()}", None)
            if key is not None:
                self._app.handle_event(
                    pg.event.Event(pg.KEYDOWN, key=key, unicode=action.key.lower()))
        # move/wait：无头环境无鼠标光标，忽略

    def reset(self) -> None:
        """直接重建同种子的 Game——确定性复现，连 R 键都不用模拟。"""
        self._app.new_game(self._seed)
        self._flagged.clear()

    # ---------- 内部 ----------

    @staticmethod
    def _rgb_to_png(img) -> bytes:
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()