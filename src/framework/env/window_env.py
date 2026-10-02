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
        content_threshold: 内容校验通过阈值（子类提供 _content_score 时生效）
        auto_activate: 定位候选窗口时自动将其带到前台（终端点击会把游戏压到
            后台导致截图评分失败；激活后评分与点击才能命中真实画面）
        resolve_timeout_s: 窗口定位重试的总时限（激活失败/暂时被遮挡时反复
            重试，超时才判失败）
        resolve_interval_s: 重试间隔
    """

    def __init__(
        self,
        region: Region | None = None,
        window_title: str | None = None,
        use_ocr: bool = True,
        ocr_languages: list[str] | None = None,
        act_interval_s: float = 0.1,
        dry_run: bool = False,
        content_threshold: float = 0.5,
        auto_activate: bool = True,
        resolve_timeout_s: float = 10.0,
        resolve_interval_s: float = 1.0,
    ):
        if region is None and window_title is None:
            region = self._primary_monitor_region()
        self._region = region
        self.window_title = window_title
        self._perception = Perception(use_ocr=use_ocr, ocr_languages=ocr_languages)
        self._screen = ScreenCapture()
        self.act_interval_s = act_interval_s
        self.dry_run = dry_run
        self.content_threshold = content_threshold
        self.auto_activate = auto_activate
        self.resolve_timeout_s = resolve_timeout_s
        self.resolve_interval_s = resolve_interval_s
        self._cached_hwnd = None  # 内容校验通过的窗口句柄缓存
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

    def _activate(self, w) -> None:
        """把候选窗口带到前台（尽力而为）：前台窗口才是截屏与点击的真实目标。

        用户点终端输命令会把游戏压到后台；SetForegroundWindow 对后台进程
        可能被系统拒绝，所以失败时静默降级，由外层重试循环兜底。
        """
        if not self.auto_activate:
            return
        try:
            if getattr(w, "isMinimized", False):
                w.restore()
                time.sleep(0.2)
            w.activate()
            time.sleep(0.4)  # 等 OS 完成前置切换
        except Exception:
            try:
                w.restore()
                time.sleep(0.4)
            except Exception:
                pass

    def _resolve_region(self) -> Region:
        """当前生效的截屏区域。

        window_title 模式：枚举标题候选。若子类提供了 _content_score 内容
        校验（以游戏实际画面为参照物），对每个候选**先激活再截图**评分取
        最高分者，并缓存其窗口句柄——后续 capture/act 直接复用（跟随窗口
        移动，免重复评分）；句柄失效（窗口关闭/内容不符）时自动重新验证。
        评分不达标时不立即失败，而是在 resolve_timeout_s 内反复重试——
        覆盖"游戏被终端遮挡/激活被系统延迟"这类暂时性遮挡。
        """
        if self.window_title is None:
            return self._region

        import pygetwindow as gw

        deadline = time.time() + self.resolve_timeout_s
        report: list[str] = []
        while True:
            wins = [w for w in gw.getAllWindows()
                    if self.window_title.lower() in (w.title or "").lower()
                    and w.width > 0 and w.height > 0]
            if not wins:
                self._cached_hwnd = None
                raise RuntimeError(f"未找到标题包含 {self.window_title!r} 的窗口")

            # 已验证窗口优先复用（跟随移动，免重复评分）
            if self._cached_hwnd is not None:
                for w in wins:
                    if getattr(w, "_hWnd", None) == self._cached_hwnd:
                        self._region = (w.left, w.top, w.width, w.height)
                        return self._region
                self._cached_hwnd = None  # 缓存的窗口已关闭 → 重新验证

            self._region = (wins[0].left, wins[0].top, wins[0].width, wins[0].height)
            if type(self)._content_score is WindowEnv._content_score:
                self._activate(wins[0])
                return self._region  # 子类未提供内容校验 → 沿用首个标题候选

            best_score, best, report = -1.0, None, []
            for w in wins:
                self._activate(w)
                region = (w.left, w.top, w.width, w.height)
                try:
                    score = float(self._content_score(self._screen.capture_region(*region)))
                except Exception as e:
                    score = -1.0
                    report.append(f"  {w.title!r} 评分异常: {e}")
                    continue
                report.append(f"  {w.title!r} 内容匹配分 {score:.2f}")
                if score > best_score:
                    best_score, best = score, (w, region)
            if best is not None and best_score >= self.content_threshold:
                self._cached_hwnd = getattr(best[0], "_hWnd", None)
                self._region = best[1]
                return self._region

            if time.time() >= deadline:
                raise RuntimeError(
                    f"标题含 {self.window_title!r} 的 {len(wins)} 个候选窗口内容在 "
                    f"{self.resolve_timeout_s}s 内均未匹配（阈值 {self.content_threshold}）。"
                    f"可能原因：游戏窗口被其他窗口完全遮挡且激活失败——"
                    f"请手动点击游戏窗口后重试。\n" + "\n".join(report))
            time.sleep(self.resolve_interval_s)

    def _content_score(self, png: bytes) -> float | None:
        """内容校验钩子：候选窗口截图与目标游戏的匹配分（0~1）。

        基类返回 None = 不做内容校验（沿用首个标题候选）。
        子类覆盖此方法即可实现"以实际画面为参照物"的窗口甄别。
        """
        return None

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
