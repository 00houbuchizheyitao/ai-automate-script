"""游戏侧唯一需要实现的契约。

框架核心只认这三个方法：
- capture() 给 LLM 看世界
- act()     让 LLM 动手
- check()   给裁判哨子（标准随 Task 传入，机制归这里）

"必须的最小 + 可选的增强"：save/restore 等增强方法进可选层（v1.1）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.framework.types import Action, FrameAnalysis, Status, Task


class Environment(ABC):
    """任何游戏接入框架，只需实现这三个方法。"""

    @property
    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """(width, height)，用于动作坐标校验与裁剪。"""

    @abstractmethod
    def capture(self) -> FrameAnalysis:
        """返回当前画面（截图 + 可选的感知预分析）。"""

    @abstractmethod
    def act(self, action: Action) -> None:
        """执行一个动作（键鼠原语）。实现内自行处理节流/等待渲染。"""

    @abstractmethod
    def check(self, task: Task) -> Status:
        """核实任务成败：SUCCESS / FAIL / RUNNING。"""

    def reset(self) -> None:
        """复位到任务初始状态。默认无操作；benchmark 场景必须实现。"""
