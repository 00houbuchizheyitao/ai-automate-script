"""AgentRunner：感知-决策-执行-判分的循环编排。

decider 协议（LLM 可插拔的窄接口）：
    async def decide(prompt: str, screenshot: bytes) -> str

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

Decider = Callable[[str, bytes], Awaitable[str]]


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
    ):
        self.env = env
        self.decider = decider
        self.assembler = ContextAssembler()
        self.history = HistoryManager(window=history_window)
        self.parse_retries = parse_retries
        self.step_interval_s = step_interval_s

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

            action = await self._decide_with_retry(task, frame, prompt,
                                                   step_feedback, screen_size)
            actions.append(action)

            self.env.act(action)
            await asyncio.sleep(self.step_interval_s)

            status = self.env.check(task)
            self.history.record(step, frame.summary(), action, status)

            if status is not Status.RUNNING:
                return RunResult(status=status, steps=step, actions=actions)

            # 任务尚未完成 → 为下一步注入显式反馈（破解"原样重复同一动作"的僵死循环）
            step_feedback = (
                f"上一步你执行了 {action.describe()}，动作已执行但任务仍未完成。"
                f"请对比画面与上一步的差异，不要原样重复同一动作；"
                f"若是坐标问题，请根据目标的实际位置修正坐标。"
            )

        return RunResult(status=Status.FAIL, steps=task.timeout_steps, actions=actions)

    async def _decide_with_retry(self, task: Task, frame, base_prompt: str,
                                 step_feedback: str | None,
                                 screen_size: tuple[int, int]) -> Action:
        prompt, feedback = base_prompt, None
        for _ in range(self.parse_retries + 1):
            raw = await self.decider(prompt, frame.screenshot)
            try:
                return parse_action(raw, screen_size)
            except ActionParseError as e:
                feedback = str(e)
                prompt = self.assembler.build(
                    task=task, frame=frame, history=self.history.view(),
                    screen_size=screen_size,
                    error_feedback=feedback, step_feedback=step_feedback,
                )
        raise ActionParseError(f"重试 {self.parse_retries + 1} 次仍无法解析动作，最后错误: {feedback}")
