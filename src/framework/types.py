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
    """一帧画面的双通道表示：原图给多模态 LLM，结构化层给文本推理。

    annotated/tags：SoM（Set-of-Mark）标注——annotated 是带编号徽章的
    标注图（与 screenshot 同一画面的副本），tags 是 编号→点击目标点
    （图像坐标）的映射。Runner 负责把 LLM 引用的编号解析为坐标。
    """
    screenshot: bytes
    elements: tuple[Element, ...] = ()
    notes: str = ""
    annotated: bytes | None = None
    tags: dict[str, tuple[int, int]] | None = None
    opened_ids: frozenset[str] | None = None  # 已翻开格子的编号集合（SoM 环境）

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

ACTION_TYPES = ("key", "click", "flag", "move", "wait")

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
    id: str | None = None  # SoM 标记编号：click/flag 与 ids 二选一，由 Runner 解析为坐标
    ids: tuple[str, ...] = ()  # 多目标：一次点击/标记多个格子（Runner 逐个解析执行）
    conclusions: tuple[str, ...] = ()  # 模型本步的推理结论，存入整局结论记忆

    def validate(self) -> None:
        if self.type not in ACTION_TYPES:
            raise ValueError(f"未知动作类型: {self.type!r}，可选: {ACTION_TYPES}")
        if self.type in ("click", "flag"):
            has_xy = self.x is not None and self.y is not None
            has_id = self.id is not None or bool(self.ids)
            if not has_xy and not has_id:
                raise ValueError(f"{self.type} 需要 x/y 坐标或 id/ids 标记")
        if self.type == "key" and not self.key:
            raise ValueError("key 动作需要 key 字段")

    def describe(self) -> str:
        if self.type == "key":
            return f"key({self.key})"
        if self.type in ("click", "move"):
            if self.ids:
                return f"{self.type}(ids:{','.join(self.ids)})"
            if self.id is not None and self.x is None:
                return f"{self.type}(id:{self.id})"
            return f"{self.type}({self.x},{self.y})"
        return f"wait({self.ms}ms)"


class ActionParseError(Exception):
    """LLM 输出无法解析为合法动作。错误信息会回喂给 LLM 重试。"""


def _iter_balanced_braces(raw: str):
    """按出现顺序产出文本中所有平衡的 {...} 片段。

    LLM 回复的推理正文常含非 JSON 的花括号记号（扫雷推理的集合
    {1, 10}、{31, 32, 33}），逐段尝试解析而不是抓第一个就定生死。
    字符串字面量内的花括号/引号不参与配对（JSON 字符串可能含 {}）。
    """
    depth = start = 0
    in_str = esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                yield raw[start:i + 1]


def _balanced_span(text: str, open_idx: int) -> int | None:
    """text[open_idx]（'[' 或 '{'）起平衡括号片段的结束索引；未闭合返回 None。

    字符串字面量内的括号/引号不参与配对。
    """
    opener = text[open_idx]
    closer = "]" if opener == "[" else "}"
    depth = in_str = esc = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = 0
            elif ch == "\\":
                esc = 1
            elif ch == '"':
                in_str = 0
            continue
        if ch == '"':
            in_str = 1
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    return None


def _collect_bare_conclusions(raw: str, pool: list[str]) -> None:
    """收集非对象形态的结论数组（GLM 输出格式随机变化，实测三种漏网形态）：

    1. 裸键值：conclusions: [...] / "conclusions": [...]（无花括号包裹）
    2. 结论标题（# ...结论...）与下一个标题之间的裸数组 ["...", ...]
    收集到的数组仅当全部元素为字符串时采纳；重复由调用方去重兜底。
    """
    for m in re.finditer(r'"?conclusions"?\s*[:=]\s*\[', raw):
        start = m.end() - 1  # '[' 的位置（正则已要求数组紧跟键）
        end = _balanced_span(raw, start)
        if end is None:
            continue
        try:
            arr = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(arr, list):
            pool.extend(c for c in map(str, arr))

    title = re.search(r"^#{1,6}[ \t]*[^\n]*结论[^\n]*$", raw, re.MULTILINE)
    if not title:
        return
    next_title = re.search(r"^#{1,6}[ \t]", raw[title.end():], re.MULTILINE)
    scope_end = title.end() + next_title.start() if next_title else len(raw)
    start = raw.find("[", title.end(), scope_end)
    if start == -1:
        return
    end = _balanced_span(raw[:scope_end], start)  # 数组须完整落在标题区内
    if end is None:
        return
    try:
        arr = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return
    if isinstance(arr, list):
        pool.extend(c for c in map(str, arr))


def parse_action(raw: str, screen_size: tuple[int, int] | None = None) -> Action:
    """从 LLM 原始输出中提取并校验 JSON 动作。

    动作 = 输出中含 type 的合法 JSON 对象（多个时取最后一个——模型的
    终稿习惯放在回复末尾）；推理正文里的 {...} 集合记号不是 JSON，
    逐段尝试自动跳过。conclusions 支持两种发法：随动作对象一起，或
    独立 JSON 对象——全部收集合并（去重保序）。id/ids 的坐标解析不在
    这一步（需要当前帧的标注图），由 Runner 完成。
    """
    action_data: dict | None = None
    conclusion_pool: list[str] = []
    first_failure = ""
    for candidate in _iter_balanced_braces(raw):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as e:
            if not first_failure:
                first_failure = f"{e}。片段: {candidate[:120]!r}"
            continue
        if not isinstance(data, dict):
            continue
        if data.get("type") in ACTION_TYPES:
            action_data = data  # 仅认可法动作类型——GLM 有时给结论块也配
            #   "type": "conclusions"/"conclusion" 字段，不能当成动作覆盖
            #   前面的合法 click（真实闭环第 2/4 步回归）
        if isinstance(data.get("conclusions"), list):
            conclusion_pool.extend(str(c) for c in data["conclusions"])
    _collect_bare_conclusions(raw, conclusion_pool)  # 非对象形态的结论（裸键值/标题后裸数组）
    if action_data is None:
        detail = first_failure or f"原始输出: {raw[:200]!r}"
        raise ActionParseError(f"输出中未找到含 type 的 JSON 动作。{detail}")

    data = action_data
    aid, ids = data.get("id"), data.get("ids")
    conclusions = list(dict.fromkeys(conclusion_pool))  # 去重保序
    try:
        if ids is not None and not isinstance(ids, list):
            raise ValueError("ids 必须是数组，如 \"ids\": [\"5\", \"6\"]")
        action = Action(
            type=str(data["type"]).strip().lower(),
            key=data.get("key"),
            x=data.get("x"),
            y=data.get("y"),
            ms=int(data.get("ms", 50)),
            id=str(aid) if aid is not None else None,
            ids=tuple(str(i) for i in ids) if ids else (),
            conclusions=tuple(conclusions),
        )
        action.validate()
    except (ValueError, TypeError) as e:
        raise ActionParseError(str(e))

    if screen_size and action.type in ("click", "move") and action.x is not None:
        w, h = screen_size
        action = Action(
            type=action.type,
            key=action.key,
            x=max(0, min(action.x, w - 1)),
            y=max(0, min(action.y, h - 1)),
            ms=action.ms,
            id=action.id,
            ids=action.ids,
            conclusions=action.conclusions,
        )
    return action
