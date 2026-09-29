"""框架核心类型定义。

设计原则：
- Action = 键鼠原语（游戏无关的最小词汇表），LLM 输出契约
- Task 自带成败标准的"声明"，机制由 Environment.check() 执行
- FrameAnalysis 是一帧画面的结构化表示（感知层产物）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum


class Status(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAIL = "fail"


@dataclass(frozen=True)
class Element:
    """画面中检测到的可交互目标（感知层产物，坐标即 LLM 可点击的目标）。"""
    text: str
    x: int
    y: int
    confidence: float = 1.0


@dataclass(frozen=True)
class FrameAnalysis:
    """一帧画面的双通道表示：原图给多模态 LLM，结构化层给文本推理。"""
    screenshot: bytes
    elements: tuple[Element, ...] = ()
    notes: str = ""

    def describe(self) -> str:
        """结构化通道的文本表示。"""
        if not self.elements and not self.notes:
            return "(画面无可识别文字元素)"
        lines = [f"- {e.text!r} @ ({e.x}, {e.y}) conf={e.confidence:.2f}" for e in self.elements]
        if self.notes:
            lines.insert(0, self.notes)
        return "\n".join(lines)

    def summary(self) -> str:
        """单行摘要：供历史记录压缩使用（describe() 的紧凑版）。"""
        parts = []
        if self.notes:
            parts.append(self.notes)
        if self.elements:
            shown = ", ".join(f"{e.text!r}@({e.x},{e.y})" for e in self.elements[:5])
            more = f" 等{len(self.elements)}项" if len(self.elements) > 5 else ""
            parts.append(f"可见元素: {shown}{more}")
        return "；".join(parts) if parts else "(画面无明显变化特征)"


@dataclass(frozen=True)
class Task:
    """任务 = 目标声明 + 约束。成败"标准"随 Task 传入，机制归 Environment.check()。"""
    goal: str
    timeout_steps: int = 30
    meta: dict = field(default_factory=dict)


# ---------- 动作词汇表（v0：键鼠原语，游戏无关的最大公约数） ----------

ACTION_TYPES = ("key", "click", "move", "wait")

ACTION_SCHEMA_HINT = """\
每次只能输出一个 JSON 动作，格式如下（不要输出其他内容）：
{"type": "key", "key": "w"}          # 按键（如 w/a/s/d/space/enter/esc）
{"type": "click", "x": 320, "y": 400} # 在屏幕坐标处点击
{"type": "move", "x": 320, "y": 400}  # 移动鼠标到坐标
{"type": "wait", "ms": 500}           # 等待毫秒
"""


@dataclass(frozen=True)
class Action:
    type: str
    key: str | None = None
    x: int | None = None
    y: int | None = None
    ms: int = 50

    def validate(self) -> None:
        if self.type not in ACTION_TYPES:
            raise ValueError(f"未知动作类型: {self.type!r}，可选: {ACTION_TYPES}")
        if self.type in ("click", "move") and (self.x is None or self.y is None):
            raise ValueError(f"{self.type} 需要 x/y 坐标")
        if self.type == "key" and not self.key:
            raise ValueError("key 动作需要 key 字段")

    def describe(self) -> str:
        if self.type == "key":
            return f"key({self.key})"
        if self.type in ("click", "move"):
            return f"{self.type}({self.x},{self.y})"
        return f"wait({self.ms}ms)"


class ActionParseError(Exception):
    """LLM 输出无法解析为合法动作。错误信息会回喂给 LLM 重试。"""


def parse_action(raw: str, screen_size: tuple[int, int] | None = None) -> Action:
    """从 LLM 原始输出中提取并校验第一个 JSON 动作。"""
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        raise ActionParseError(f"输出中未找到 JSON 动作。原始输出: {raw[:200]!r}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ActionParseError(f"JSON 解析失败: {e}。原始输出: {match.group(0)[:200]!r}")

    if not isinstance(data, dict) or "type" not in data:
        raise ActionParseError(f"JSON 缺少 type 字段: {data}")

    try:
        action = Action(
            type=str(data["type"]).strip().lower(),
            key=data.get("key"),
            x=data.get("x"),
            y=data.get("y"),
            ms=int(data.get("ms", 50)),
        )
        action.validate()
    except (ValueError, TypeError) as e:
        raise ActionParseError(str(e))

    if screen_size and action.type in ("click", "move"):
        w, h = screen_size
        action = Action(
            type=action.type,
            key=action.key,
            x=max(0, min(action.x, w - 1)),
            y=max(0, min(action.y, h - 1)),
            ms=action.ms,
        )
    return action
