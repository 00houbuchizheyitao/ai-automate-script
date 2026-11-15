"""WindowEnv 冒烟测试：抽象性、坐标平移、真实截屏（需桌面会话）。"""
import pytest

from game_agent.framework import WindowEnv
from game_agent.framework.types import Action, Status


class _Probe(WindowEnv):
    """最小具体子类：check 永远 RUNNING（测试只关心通用层）。"""

    def check(self, task) -> Status:
        return Status.RUNNING


def test_window_env_still_abstract():
    """check 未实现 → 不能直接实例化（这正是留给适配者的口子）"""
    with pytest.raises(TypeError):
        WindowEnv(region=(0, 0, 100, 100))


def test_coordinate_translation():
    """图像坐标 → 屏幕绝对坐标的平移（region 原点 100,200）"""
    env = _Probe(region=(100, 200, 800, 600), use_ocr=False, dry_run=True)

    env.act(Action(type="click", x=10, y=20))
    assert env.last_act[1] == (110, 220)

    env.act(Action(type="move", x=0, y=0))
    assert env.last_act[1] == (100, 200)

    env.act(Action(type="key", key="Enter"))
    assert env.last_act[1] is None  # 按键动作无坐标


def test_screen_size_matches_region():
    env = _Probe(region=(100, 200, 800, 600), use_ocr=False)
    assert env.screen_size == (800, 600)


def test_capture_returns_png_frame():
    """真实截屏冒烟：区域截图应为合法 PNG（需要桌面会话）"""
    env = _Probe(region=(0, 0, 400, 300), use_ocr=False)
    frame = env.capture()
    assert frame.screenshot.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(frame.screenshot) > 1_000  # 合法 PNG 必然超过此下限（纯色屏也有数KB）


def test_resolve_region_retries_until_content_visible(monkeypatch):
    """遮挡恢复场景：前几次截图是白底遮挡物（评分0），窗口露出后自动通过；
    不应在首次评分失败时立即放弃（用户点终端会把游戏压到后台）"""
    import io
    import sys
    import types

    import pytest
    from PIL import Image

    from game_agent.framework.env.window_env import WindowEnv

    class _GrayEnv(WindowEnv):
        def _content_score(self, png: bytes) -> float:
            import numpy as np
            img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
            return 1.0 if img.mean() < 150 else 0.0  # 深灰=游戏露出

        def check(self, task):
            from game_agent.framework import Status
            return Status.RUNNING

    calls = {"n": 0}

    class FakeWin:
        def __init__(self):
            self.title = "扫雷 seed=1"
            self.left, self.top, self.width, self.height = 10, 10, 376, 399
            self._hWnd = 12345
            self.activated = False

        def activate(self):
            self.activated = True

    win = FakeWin()
    fake_gw = types.SimpleNamespace(getAllWindows=lambda: [win])
    monkeypatch.setitem(sys.modules, "pygetwindow", fake_gw)

    env = _GrayEnv(window_title="扫雷", use_ocr=False, dry_run=True,
                   resolve_timeout_s=5.0, resolve_interval_s=0.1,
                   content_threshold=0.5)

    def fake_capture_region(left, top, width, height):
        calls["n"] += 1
        color = (255, 255, 255) if calls["n"] <= 2 else (100, 100, 100)
        img = Image.new("RGB", (width, height), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr(env._screen, "capture_region", fake_capture_region)

    region = env._resolve_region()
    assert region == (10, 10, 376, 399)
    assert calls["n"] >= 3                    # 前两次遮挡未通过，重试后通过
    assert win.activated                      # 每轮候选都被尝试激活


def test_resolve_region_timeout_raises(monkeypatch):
    """持续被遮挡：超过 resolve_timeout_s 才判失败，错误含诊断报告"""
    import io
    import sys
    import types

    import pytest
    from PIL import Image

    from game_agent.framework.env.window_env import WindowEnv

    class _WhiteEnv(WindowEnv):
        def _content_score(self, png: bytes) -> float:
            return 0.0  # 永远不匹配（模拟持续遮挡）

        def check(self, task):
            from game_agent.framework import Status
            return Status.RUNNING

    win = types.SimpleNamespace(
        title="扫雷 seed=1", left=10, top=10, width=376, height=399,
        _hWnd=999, activate=lambda: None, isMinimized=False)
    fake_gw = types.SimpleNamespace(getAllWindows=lambda: [win])
    monkeypatch.setitem(sys.modules, "pygetwindow", fake_gw)

    env = _WhiteEnv(window_title="扫雷", use_ocr=False, dry_run=True,
                    resolve_timeout_s=0.5, resolve_interval_s=0.1,
                    content_threshold=0.5)

    def fake_capture_region(left, top, width, height):
        img = Image.new("RGB", (width, height), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr(env._screen, "capture_region", fake_capture_region)

    with pytest.raises(RuntimeError, match="均未匹配"):
        env._resolve_region()
