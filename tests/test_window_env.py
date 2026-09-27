"""WindowEnv 冒烟测试：抽象性、坐标平移、真实截屏（需桌面会话）。"""
import pytest

from src.framework import WindowEnv
from src.framework.types import Action, Status


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
