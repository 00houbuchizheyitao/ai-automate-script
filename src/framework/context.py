"""上下文组装器：信息质量的执行者。

只做选择与排版，不采集数据。三条纪律：
- 目标常驻（防第50步失忆）
- 历史分层（HistoryManager 已切片，这里只拼装）
- 当前帧双通道（结构化文本 + 原图由 decider 层附给多模态 LLM）
"""
from __future__ import annotations

from src.framework.types import ACTION_SCHEMA_HINT, FrameAnalysis, Task
from src.framework.history import HistoryView


class ContextAssembler:
    def build(self, task: Task, frame: FrameAnalysis, history: HistoryView,
              error_feedback: str | None = None) -> str:
        parts = [
            f"# 任务目标（每步都有效）\n{task.goal}",
            f"\n# 可用动作\n{ACTION_SCHEMA_HINT}",
            f"\n# 屏幕尺寸\n{self._screen_size_line(frame)}",
            f"\n# 历史操作\n{history.render()}",
        ]
        if error_feedback:
            parts.append(f"\n# 上一次输出无效，请修正\n{error_feedback}")
        parts.append(
            f"\n# 当前画面可识别元素\n{frame.describe()}"
            "\n\n# 你的决策\n只输出一个 JSON 动作："
        )
        return "\n".join(parts)

    @staticmethod
    def _screen_size_line(frame: FrameAnalysis) -> str:
        return (f"图像为 PNG，坐标原点在左上角，坐标系与图像像素一致。"
                f"可识别元素数: {len(frame.elements)}")
