"""AgentRunner：感知-决策-执行-判分的循环编排。

decider 协议（LLM 可插拔的窄接口）：
    async def decide(prompt: str, images: list[bytes]) -> str
    images[0] = 原始画面；images[1:] = 附加图（如 SoM 标注图）

解析失败不崩循环——错误信息作为反馈重试（管道可靠性的关键）。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from game_agent.framework.context import ContextAssembler
from game_agent.framework.env.base import Environment
from game_agent.framework.history import HistoryManager
from game_agent.framework.types import Action, ActionParseError, Status, Task, parse_action

Decider = Callable[[str, list[bytes]], Awaitable[str]]


@dataclass
class RunResult:
    status: Status
    steps: int
    actions: list[Action] = field(default_factory=list)
    conclusions: list[str] = field(default_factory=list)  # 整局累积的推理结论
    usage: dict = field(default_factory=dict)  # token/耗时合计（含重试调用）


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
        trace_logger: "RunTraceLogger | None" = None,
        on_step: "Callable | None" = None,
        include_action_options: bool = True,
    ):
        self.env = env
        self.decider = decider
        self.assembler = ContextAssembler()
        self.history = HistoryManager(window=history_window)
        self.parse_retries = parse_retries
        self.step_interval_s = step_interval_s
        self.stagnation_feedback_at = stagnation_feedback_at
        self.tracer = trace_logger
        self.on_step = on_step  # 每步结束回调 on_step(step, subs, status)，供脚本实时打印
        # Function Calling 模式由 decider 侧声明动作格式 → prompt 省略行动
        # 选项段（Runner 不关心协议细节，只关心"要不要在 prompt 里写格式"）
        self.include_action_options = include_action_options
        self._usage_total = self._empty_usage()

    @staticmethod
    def _empty_usage() -> dict:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "prompt_eval_ms": 0.0,
            "eval_ms": 0.0,
            "total_ms": 0.0,
            "calls": 0,
            "max_seq": 0,
            "max_prompt_tokens": 0,
            "max_completion_tokens": 0,
            "length_stops": 0,
        }

    def _accumulate_usage(self, usage: dict | None) -> None:
        """累加一次 LLM 调用的用量；decider 不支持 usage 时静默跳过。"""
        if not usage:
            return
        self._usage_total["calls"] += 1
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        for key in ("prompt_tokens", "completion_tokens"):
            self._usage_total[key] += int(usage.get(key) or 0)
        for key in ("prompt_eval_ms", "eval_ms", "total_ms"):
            self._usage_total[key] += float(usage.get(key) or 0)
        # 单次请求的完整序列长度 = prompt + completion，用于确定 num_ctx
        self._usage_total["max_seq"] = max(
            self._usage_total["max_seq"], prompt_tokens + completion_tokens)
        self._usage_total["max_prompt_tokens"] = max(
            self._usage_total["max_prompt_tokens"], prompt_tokens)
        self._usage_total["max_completion_tokens"] = max(
            self._usage_total["max_completion_tokens"], completion_tokens)
        if usage.get("done_reason") == "length":
            self._usage_total["length_stops"] += 1

    async def run(self, task: Task) -> RunResult:
        self.env.reset()
        self.history.clear()
        self._usage_total = self._empty_usage()
        actions: list[Action] = []
        step_feedback: str | None = None
        conclusions: list[str] = []       # 整局累积（RunResult 汇总用）
        last_conclusions: list[str] = []  # 上一步 LLM 发回的结论——prompt 只注入最近一批
        step = 0
        finish_reason = "运行中断（未到达任何结束点）"

        try:
            for step in range(1, task.timeout_steps + 1):
                frame = self.env.capture()
                screen_size = self.env.screen_size
                prompt = self.assembler.build(task, frame, self.history.view(),
                                              screen_size=screen_size,
                                              step_feedback=step_feedback,
                                              conclusions=last_conclusions,
                                              include_action_options=self.include_action_options)
                # 多图供给：原图 + 附加图（SoM 标注图等）
                images = [frame.screenshot]
                if frame.annotated:
                    images.append(frame.annotated)

                subs, step_conclusions = await self._decide_with_retry(
                    task, frame, prompt, step_feedback, screen_size, step=step,
                    conclusions=last_conclusions)
                for sub in subs:  # 多格动作逐个执行（click 多格 / flag 多格）
                    self.env.act(sub)
                    actions.append(sub)
                    await asyncio.sleep(self.step_interval_s)
                conclusions.extend(step_conclusions)      # 全量累积供 RunResult 汇总
                last_conclusions = list(step_conclusions)  # 下一步只注入这一批（旧结论对当前局面已过时）

                status = self.env.check(task)
                self.history.record(step, frame.summary(), actions=subs, status=status)
                if self.on_step:
                    try:
                        self.on_step(step, subs, status)
                    except Exception:
                        pass  # 回调异常不影响主循环

                if status is not Status.RUNNING:
                    finish_reason = f"任务判定结束：{status.value}（第 {step} 步判定）"
                    return RunResult(status=status, steps=step, actions=actions,
                                     conclusions=list(conclusions),
                                     usage=dict(self._usage_total))

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
                    executed = ", ".join(a.describe() for a in subs)
                    step_feedback = (
                        f"上一步你执行了 [{executed}]，动作已执行但任务仍未完成。"
                        f"请对比画面与上一步的差异，不要原样重复同一动作；"
                        f"若是坐标问题，请根据目标的实际位置修正坐标。"
                    )

            finish_reason = f"步数耗尽：{task.timeout_steps} 步上限用完仍未达标，判定 fail"
            return RunResult(status=Status.FAIL, steps=task.timeout_steps, actions=actions,
                             conclusions=list(conclusions),
                             usage=dict(self._usage_total))
        except Exception as e:
            # 异常也要在追踪留档——复盘时区分"游戏判负"与"框架崩溃"
            finish_reason = f"异常中断：{type(e).__name__}: {e}"
            raise
        finally:
            if self.tracer:
                self.tracer.log_finish(
                    reason=finish_reason, steps=step, max_steps=task.timeout_steps,
                    actions=actions, conclusions=conclusions,
                    usage=self._usage_total)

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
                                 screen_size: tuple[int, int],
                                 step: int = 0,
                                 conclusions: list[str] | None = None
                                 ) -> tuple[list[Action], tuple[str, ...]]:
        """一次 LLM 决策 → (具体坐标动作列表, 本步推理结论)。

        解析 + 编号解析（id/ids → 坐标），conclusions 随动作携带不丢失。
        每次 LLM 调用（含重试）都记录到追踪日志；重试重建 prompt 时补传
        conclusions，保证 SoM 三段结构完整。
        """
        prompt, feedback = base_prompt, None
        images = [frame.screenshot] + ([frame.annotated] if frame.annotated else [])
        for _ in range(self.parse_retries + 1):
            t0 = time.monotonic()
            raw = await self.decider(prompt, images)
            elapsed = time.monotonic() - t0  # 本次 LLM 调用耗时（含长思考）
            usage = getattr(self.decider, "last_usage", None)
            thinking = getattr(self.decider, "last_thinking", "")
            self._accumulate_usage(usage)
            try:
                action = parse_action(raw, screen_size)
                subs, _ = self._resolve_tag(action, frame)
                if self.tracer:
                    self.tracer.log_step(
                        step=step, prompt=prompt, images=images, raw_output=raw,
                        parsed=[a.describe() for a in subs],
                        status="parsed", conclusions=list(action.conclusions),
                        elapsed_s=elapsed, usage=usage, thinking=thinking)
                return subs, action.conclusions
            except ActionParseError as e:
                feedback = str(e)
                if self.tracer:
                    self.tracer.log_step(
                        step=step, prompt=prompt, images=images, raw_output=raw,
                        parsed=None, status=f"parse_error: {e}", conclusions=[],
                        elapsed_s=elapsed, usage=usage, thinking=thinking)
                prompt = self.assembler.build(
                    task=task, frame=frame, history=self.history.view(),
                    screen_size=screen_size, error_feedback=feedback,
                    step_feedback=step_feedback,
                    conclusions=conclusions or [],
                    include_action_options=self.include_action_options)
        raise ActionParseError(f"重试 {self.parse_retries + 1} 次仍无法解析动作，最后错误: {feedback}")

    @staticmethod
    def _resolve_tag(action: Action, frame) -> tuple[list[Action], tuple[str, ...]]:
        """SoM 符号解析：编号/编号数组 → 具体坐标动作列表（结论透传到首个动作）。

        id 或 ids 中的每个编号查当前帧标注图换算坐标；未知编号视为解析
        错误——错误反馈会列出可用编号，走重试路径。
        """
        if not action.ids and not action.id:
            return [action], action.conclusions
        tags = frame.tags or {}
        wanted = list(action.ids) or ([action.id] if action.id else [])
        resolved: list[Action] = []
        for tid in wanted:
            if tid not in tags:
                available = ", ".join(sorted(tags, key=lambda s: int(s) if s.isdigit() else 0)) or "无"
                raise ActionParseError(
                    f"编号 {tid!r} 不在当前标注图中（该格子可能已翻开）。"
                    f"可用编号: {available}")
            x, y = tags[tid]
            resolved.append(Action(type=action.type, x=x, y=y, ms=action.ms))
        if resolved and action.conclusions:  # 结论挂到首个子动作，随循环进入结论记忆
            first = resolved[0]
            resolved[0] = Action(type=first.type, key=first.key, x=first.x, y=first.y,
                                 ms=first.ms, conclusions=action.conclusions)
        return resolved, action.conclusions
