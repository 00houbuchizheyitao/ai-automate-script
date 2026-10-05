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
              screen_size: tuple[int, int] | None = None,
              error_feedback: str | None = None,
              step_feedback: str | None = None) -> str:
        if frame.tags:
            # SoM 极简模式：信息 = 任务目标 + 可翻开的格子编号（+ 附图）。
            # 局面理解完全交给模型看原图；已翻开的格子不在编号列表里，
            # 模型引用其编号会被 Runner 拒绝并获得纠错反馈。
            ids = ", ".join(sorted(frame.tags, key=lambda s: int(s) if s.isdigit() else 0))
            parts = [task.goal,
                     f"\n# 可翻开的格子\n{ids}",
                     '\n翻开某个格子输出：{"type": "click", "id": "编号"}']
            if error_feedback:
                parts.append(f"\n# 上一次输出无效，请修正\n{error_feedback}")
            return "\n".join(parts)

        # 完整模式（无 SoM 标注的环境）：全量信息供给
        parts = [
            f"# 任务目标（每步都有效）\n{task.goal}",
            f"\n# 可用动作\n{ACTION_SCHEMA_HINT}",
            f"\n# 屏幕尺寸\n{self._screen_size_line(screen_size, frame)}",
            f"\n# 历史操作\n{history.render()}",
        ]
        if step_feedback:
            parts.append(f"\n# 上一步反馈\n{step_feedback}")
        if error_feedback:
            parts.append(f"\n# 上一次输出无效，请修正\n{error_feedback}")
        parts.append(
            f"\n# 当前画面可识别元素\n{frame.describe()}"
            "\n\n# 你的决策\n只输出一个 JSON 动作："
        )
        return "\n".join(parts)

    @staticmethod
    def _som_line(frame: FrameAnalysis) -> str:
        return ("本次请求附带两张图：第一张是原始画面（用于读取数字等细节），"
                "第二张是同一画面的 SoM 编号标注图（每个可点击的深灰格子左上角"
                "有品红色编号徽章）。点击格子时直接引用编号："
                '{"type": "click", "id": "编号"}，无需坐标。'
                f"当前可用编号数: {len(frame.tags or {})}。"
                "若引用已翻开的格子编号会被拒绝。")

    @staticmethod
    def _screen_size_line(screen_size: tuple[int, int] | None,
                          frame: FrameAnalysis) -> str:
        if screen_size:
            w, h = screen_size
            base = (f"图像分辨率 {w}×{h} 像素，坐标原点在左上角，"
                    f"坐标范围 x∈[0,{w - 1}]，y∈[0,{h - 1}]。")
        else:
            base = "图像为 PNG，坐标原点在左上角，坐标系与图像像素一致。"
        return base + f"可识别元素数: {len(frame.elements)}"
