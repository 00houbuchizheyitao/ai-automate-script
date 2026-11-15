"""上下文组装器：信息质量的执行者。

只做选择与排版，不采集数据。三条纪律：
- 目标常驻（防第50步失忆）
- 历史分层（HistoryManager 已切片，这里只拼装）
- 当前帧双通道（结构化文本 + 原图由 decider 层附给多模态 LLM）
"""
from __future__ import annotations

from game_agent.framework.types import ACTION_SCHEMA_HINT, FrameAnalysis, Task
from game_agent.framework.history import HistoryView


class ContextAssembler:
    def build(self, task: Task, frame: FrameAnalysis, history: HistoryView,
              screen_size: tuple[int, int] | None = None,
              error_feedback: str | None = None,
              step_feedback: str | None = None,
              conclusions: list[str] | None = None,
              include_action_options: bool = True) -> str:
        """组装发给 LLM 的完整信息。

        include_action_options=False 用于 Function Calling 模式：动作格式由
        API 层 tools schema 声明（硬约束），prompt 不再重复 JSON 写法，
        只保留任务/局面/结论——两种协议下 prompt 差异即实验对照组。
        """
        if frame.tags:
            # SoM 极简模式（三段结构，固定契约）：固定信息 + 行动选项 +
            # 过往推理结论。局面理解完全交给模型看原图；已翻开的格子不在
            # 编号列表里，模型引用其编号会被 Runner 拒绝并触发重试。
            # error_feedback / step_feedback 仅完整模式消费——本结构不注入
            # 任何额外段落，解析失败重试 = 原样重发（靠模型重答）。
            ids = ", ".join(sorted(frame.tags, key=lambda s: int(s) if s.isdigit() else 0))
            fixed = task.goal + (
                "\n其中有橙色三角形标记的格子是你之前推理出来有雷的格子。"
                if self._has_flags(frame) else "")
            parts = [fixed,
                     f"\n# 可翻开的格子\n{ids}"]
            if include_action_options:
                parts.append("\n# 行动选项\n"
                             "翻开格子（一个或多个）：{\"type\": \"click\", \"id\": \"编号\"} 或 "
                             "{\"type\": \"click\", \"ids\": [\"编号1\", \"编号2\"]}\n"
                             "标记雷格（一个或多个）：{\"type\": \"flag\", \"id\": \"编号\"} 或 "
                             "{\"type\": \"flag\", \"ids\": [\"编号1\", \"编号2\"]}")
            if conclusions:
                numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(conclusions, 1))
                parts.append(f"\n# 上一步推理结论（有助于你本次推理）\n{numbered}")
            if include_action_options:
                parts.append("\n# 你推理出的结论（可选）\n"
                             "你推理出来的结论如果认为对下一步有用，也可以发回来，"
                             "下次推理会再发给你帮助你推理——比如你这步推理出某 2 个格子必有一个是雷，"
                             "那这就是值得发回来的结论。发回格式："
                             "\"conclusions\": [\"结论1\", \"结论2\"]")
            else:
                parts.append("\n# 你推理出的结论（可选）\n"
                             "如果认为对下一步有用，把它放进动作调用的可选参数 "
                             "conclusions（字符串数组）——比如你这步推理出某 2 个格子必有一个是雷，"
                             "那这就是值得下次复用的结论。")
            return "\n".join(parts)

        # 完整模式（无 SoM 标注的环境）：全量信息供给
        parts = [
            f"# 任务目标（每步都有效）\n{task.goal}",
            (f"\n# 可用动作\n{ACTION_SCHEMA_HINT}" if include_action_options
             else "\n# 可用动作\n通过工具调用执行动作（参数 ids/conclusions 见工具定义）。"),
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
    def _has_flags(frame: FrameAnalysis) -> bool:
        """notes 中是否声明了橙三角标记（即本局存在已标记雷格）"""
        return bool(frame.notes) and "橙" in frame.notes

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
