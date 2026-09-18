"""历史管理器：记录每步 (分析摘要, 动作, 结果)，对外只暴露 recent/summary 视图。

v0：滑动窗口 + 朴素摘要。v1 升级点：向量化检索、跨窗口笔记（Astra 那套）——只动这个类。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.framework.types import Action, Status


@dataclass
class Step:
    index: int
    analysis_summary: str
    action: Action
    status: Status


@dataclass
class HistoryView:
    """喂给 LLM 的历史切片：目标常驻由 ContextAssembler 负责，这里只管过程。"""
    lines: list[str] = field(default_factory=list)

    def render(self) -> str:
        if not self.lines:
            return "(尚无历史，这是第一步)"
        return "\n".join(self.lines)


class HistoryManager:
    def __init__(self, window: int = 5):
        self.window = window
        self._steps: list[Step] = []

    def record(self, step_index: int, analysis_summary: str, action: Action, status: Status) -> None:
        self._steps.append(Step(step_index, analysis_summary, action, status))

    def view(self) -> HistoryView:
        """最近 window 步全量，更早的压成一行摘要（信息选择性供给）。"""
        lines: list[str] = []
        older = self._steps[:-self.window]
        if older:
            fails = sum(1 for s in older if s.status == Status.FAIL)
            lines.append(
                f"(更早 {len(older)} 步摘要: "
                f"动作依次为 {', '.join(s.action.describe() for s in older[-5:])}"
                + (f"；其中 {fails} 步后未达标" if fails else "") + ")"
            )
        for s in self._steps[-self.window:]:
            lines.append(
                f"第{s.index}步: 画面={s.analysis_summary or '(同前)'} "
                f"→ 动作={s.action.describe()} → 状态={s.status.value}"
            )
        return HistoryView(lines=lines)

    def clear(self) -> None:
        self._steps.clear()
