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
from src.framework.perception import Perception
from src.framework.types import Action, ActionParseError, Status, Task, parse_action

Decider = Callable[[str, bytes], Awaitable[str]]


@dataclass
class RunResult:
    status: Status
    steps: int
    actions: list[Action] = field(default_factory=list)


class AgentRunner:
    def __init__(
        self,
        env: Environment,
        decider: Decider,
        perception: Perception | None = None,
        history_window: int = 5,
        parse_retries: int = 2,
        step_interval_s: float = 0.2,
    ):
        self.env = env
        self.decider = decider
        self.perception = perception or Perception(use_ocr=False)
        self.assembler = ContextAssembler()
        self.history = HistoryManager(window=history_window)
        self.parse_retries = parse_retries
        self.step_interval_s = step_interval_s

    async def run(self, task: Task) -> RunResult:
        self.env.reset()
        self.history.clear()
        actions: list[Action] = []

        for step in range(1, task.timeout_steps + 1):
            frame = self.env.capture()
            prompt = self.assembler.build(task, frame, self.history.view())

            action = await self._decide_with_retry(task, frame, prompt)
            actions.append(action)

            self.env.act(action)
            await asyncio.sleep(self.step_interval_s)

            status = self.env.check(task)
            self.history.record(step, "", action, status)

            if status is not Status.RUNNING:
                return RunResult(status=status, steps=step, actions=actions)

        return RunResult(status=Status.FAIL, steps=task.timeout_steps, actions=actions)

    async def _decide_with_retry(self, task: Task, frame, base_prompt: str) -> Action:
        prompt, feedback = base_prompt, None
        for _ in range(self.parse_retries + 1):
            raw = await self.decider(prompt, frame.screenshot)
            try:
                return parse_action(raw, self.env.screen_size)
            except ActionParseError as e:
                feedback = str(e)
                prompt = self.assembler.build(
                    task=task, frame=frame, history=self.history.view(),
                    error_feedback=feedback,
                )
        raise ActionParseError(f"重试 {self.parse_retries + 1} 次仍无法解析动作，最后错误: {feedback}")
