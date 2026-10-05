"""AgentRunner：感知-决策-执行-判分的循环编排。

decider 协议（LLM 可插拔的窄接口）：
    async def decide(prompt: str, images: list[bytes]) -> str
    images[0] = 原始画面；images[1:] = 附加图（如 SoM 标注图）

解析失败不崩循环——错误信息作为反馈重试（管道可靠性的关键）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from src.framework.context import ContextAssembler
from src.framework.env.base import Environment
from src.framework.history import HistoryManager
from src.framework.types import Action, ActionParseError, Status, Task, parse_action

Decider = Callable[[str, list[bytes]], Awaitable[str]]


@dataclass
class RunResult:
    status: Status
    steps: int
    actions: list[Action] = field(default_factory=list)


class AgentRunner:
    """注意：感知（Perception）由 Environment.capture() 内部负责组装，
    Runner 只消费成品 FrameAnalysis——感知的调用权在适配者手里。"""

    def __init__(
        self,
        env: Environment,
        decider: Decider,
        history_window: int = 5,
        parse_retries: int = 2,
        step_interval_s: float = 0.2,
        stagnation_feedback_at: int = 3,
    ):
        self.env = env
        self.decider = decider
        self.assembler = ContextAssembler()
        self.history = HistoryManager(window=history_window)
        self.parse_retries = parse_retries
        self.step_interval_s = step_interval_s
        self.stagnation_feedback_at = stagnation_feedback_at

    async def run(self, task: Task) -> RunResult:
        self.env.reset()
        self.history.clear()
        actions: list[Action] = []
        step_feedback: str | None = None

        for step in range(1, task.timeout_steps + 1):
            frame = self.env.capture()
            screen_size = self.env.screen_size
            prompt = self.assembler.build(task, frame, self.history.view(),
                                          screen_size=screen_size,
                                          step_feedback=step_feedback)
            # 多图供给：原图 + 附加图（SoM 标注图等）
            images = [frame.screenshot]
            if frame.annotated:
                images.append(frame.annotated)

            action = await self._decide_with_retry(task, frame, prompt,
                                                   step_feedback, screen_size)
            actions.append(action)

            self.env.act(action)
            await asyncio.sleep(self.step_interval_s)

            status = self.env.check(task)
            self.history.record(step, frame.summary(), action, status)

            if status is not Status.RUNNING:
                return RunResult(status=status, steps=step, actions=actions)

            # 僵滞检测：连续 N 次完全相同的非等待动作 → 反馈升格为强警告
            identical = self._consecutive_identical_count(actions)
            if identical >= self.stagnation_feedback_at:
                tried = "、".join(dict.fromkeys(a.describe() for a in actions))
                step_feedback = (
                    f"警告：你已连续 {identical} 次执行完全相同的动作"
                    f"（尝试过的动作: {tried}），任务零进展。"
                    f"重复已执行过的动作不可能推进任务——你必须改变行为："
                    f"选择一个与之前所有尝试都不同的坐标或动作类型。"
                )
            else:
                # 任务尚未完成 → 为下一步注入显式反馈
                step_feedback = (
                    f"上一步你执行了 {action.describe()}，动作已执行但任务仍未完成。"
                    f"请对比画面与上一步的差异，不要原样重复同一动作；"
                    f"若是坐标问题，请根据目标的实际位置修正坐标。"
                )

        return RunResult(status=Status.FAIL, steps=task.timeout_steps, actions=actions)

    @staticmethod
    def _consecutive_identical_count(actions: list[Action]) -> int:
        """末尾连续完全相同的非等待动作数（wait 重复是合法行为，不计）。"""
        if not actions or actions[-1].type == "wait":
            return 0
        last = actions[-1]
        identity = (last.type, last.key, last.x, last.y)
        count = 0
        for a in reversed(actions):
            if a.type == "wait":
                break
            if (a.type, a.key, a.x, a.y) == identity:
                count += 1
            else:
                break
        return count

    async def _decide_with_retry(self, task: Task, frame, base_prompt: str,
                                 step_feedback: str | None,
                                 screen_size: tuple[int, int]) -> Action:
        prompt, feedback = base_prompt, None
        images = [frame.screenshot] + ([frame.annotated] if frame.annotated else [])
        for _ in range(self.parse_retries + 1):
            raw = await self.decider(prompt, images)
            try:
                action = parse_action(raw, screen_size)
                action = self._resolve_tag(action, frame)
                return action
            except ActionParseError as e:
                feedback = str(e)
                prompt = self.assembler.build(
                    task=task, frame=frame, history=self.history.view(),
                    screen_size=screen_size,
                    error_feedback=feedback, step_feedback=step_feedback,
                )
        raise ActionParseError(f"重试 {self.parse_retries + 1} 次仍无法解析动作，最后错误: {feedback}")

    @staticmethod
    def _resolve_tag(action: Action, frame) -> Action:
        """SoM 符号解析：编号 → 图像坐标（用户所说的"符号模块"）。

        未知编号视为解析错误——错误反馈会列出可用编号，走重试路径。
        """
        if not action.id:
            return action
        tags = frame.tags or {}
        if action.id not in tags:
            available = ", ".join(sorted(tags, key=lambda s: int(s) if s.isdigit() else 0)) or "无"
            raise ActionParseError(
                f"编号 {action.id!r} 不在当前标注图中（该格子可能已翻开）。"
                f"可用编号: {available}")
        x, y = tags[action.id]
        return Action(type=action.type, key=action.key, x=x, y=y,
                      ms=action.ms, id=action.id)
