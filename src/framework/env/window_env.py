"""桌面窗口游戏的通用 Environment 实现。

适配桌面窗口游戏只需继承本类并实现 check()（benchmark 场景再加 reset()）：
capture（截屏 + OCR 感知）与 act（键鼠原语 → pyautogui）对所有桌面游戏通用，
差异只在构造参数——截哪块区域、是否 OCR、执行节奏。

坐标约定：LLM 看到的图像是 region 内的画面，坐标原点在 region 左上角；
act() 自动把图像坐标平移为屏幕绝对坐标后再注入键鼠事件。

注意：window_title 模式按窗口外框定位（含标题栏/边框），需要精确客户区时用
region 显式指定。pyautogui/pygetwindow 均为惰性导入，MockEnv 等纯合成场景
不触碰 GUI 依赖。
"""
from __future__ import annotations

import time

from src.framework.env.base import Environment
from src.framework.perception import Perception
from src.framework.types import Action, FrameAnalysis
from src.vision.screen_capture import ScreenCapture

Region = tuple[int, int, int, int]  # (left, top, width, height)


class WindowEnv(Environment):
    """桌面窗口游戏大路货实现。

    本身仍是抽象类（check 留给子类），典型用法：

        class MyGameEnv(WindowEnv):
            def check(self, task) -> Status: ...

    参数:
        region: 截屏区域 (left, top, width, height)；None 时优先 window_title
        window_title: 窗口标题（子串模糊匹配），每次 capture 重新定位、跟随窗口移动
        use_ocr: 是否对截图跑 OCR 感知（纯图形游戏可关，省时）
        ocr_languages: OCR 语言列表，默认 ["ch_sim", "en"]
        act_interval_s: 每个动作后统一等待（给游戏渲染时间）
        dry_run: 只记录坐标翻译结果，不注入真实键鼠（调试/测试用）
    """

    def __init__(
        self,
        region: Region | None = None,
        window_title: str | None = None,
        use_ocr: bool = True,
        ocr_languages: list[str] | None = None,
        act_interval_s: float = 0.1,
        dry_run: bool = False,
    ):
        if region is None and window_title is None:
            region = self._primary_monitor_region()
        self._region = region
        self.window_title = window_title
        self._perception = Perception(use_ocr=use_ocr, ocr_languages=ocr_languages)
        self._screen = ScreenCapture()
        self.act_interval_s = act_interval_s
        self.dry_run = dry_run
        self.last_act: tuple[Action, tuple[int, int] | None] | None = None

    # ---------- 区域解析 ----------

    @staticmethod
    def _primary_monitor_region() -> Region:
        cap = ScreenCapture()
        try:
            monitors = cap.get_monitor_info()
            m = monitors[1] if len(monitors) > 1 else monitors[0]
            return (m["left"], m["top"], m["width"], m["height"])
        finally:
            cap.close()

    def _resolve_region(self) -> Region:
        """当前生效的截屏区域。window_title 模式每次重新定位（跟随窗口移动）。"""
        if self.window_title is None:
            return self._region

        import pygetwindow as gw

        wins = [w for w in gw.getAllWindows()
                if self.window_title.lower() in (w.title or "").lower()]
        if not wins:
            raise RuntimeError(f"未找到标题包含 {self.window_title!r} 的窗口")
        w = wins[0]
        self._region = (w.left, w.top, w.width, w.height)
        return self._region

    # ---------- Environment 契约（check 留给子类） ----------

    @property
    def screen_size(self) -> tuple[int, int]:
        _, _, width, height = self._resolve_region()
        return (width, height)

    def capture(self) -> FrameAnalysis:
        left, top, width, height = self._resolve_region()
        png = self._screen.capture_region(left, top, width, height)
        return self._perception.analyze(png)

    def act(self, action: Action) -> None:
        left, top, _, _ = self._resolve_region()
        screen_xy: tuple[int, int] | None = None
        if action.type in ("click", "move") and action.x is not None and action.y is not None:
            screen_xy = (left + action.x, top + action.y)  # 图像坐标 → 屏幕绝对坐标
        self.last_act = (action, screen_xy)

        if self.dry_run:
            return

        import pyautogui

        if action.type == "click" and screen_xy:
            pyautogui.click(*screen_xy)
        elif action.type == "move" and screen_xy:
            pyautogui.moveTo(*screen_xy)
        elif action.type == "key" and action.key:
            pyautogui.press(action.key.lower())
        elif action.type == "wait":
            time.sleep(max(action.ms, 0) / 1000)
            return  # wait 自带时长，不再追加 interval
        time.sleep(self.act_interval_s)
