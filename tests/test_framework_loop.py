"""框架最小闭环冒烟测试：脚本化决策器 + MockEnv，不依赖 Ollama / 显示器。

跑法：pytest tests/test_framework_loop.py -v
"""
import asyncio
import json

import pytest

from src.framework import (
    Action,
    ActionParseError,
    AgentRunner,
    MockEnv,
    Status,
    Task,
    parse_action,
)


def test_mock_env_hit_and_miss():
    env = MockEnv(seed=7)
    env.set_target(400, 300)
    task = Task(goal="点击白色方块", timeout_steps=10)

    env.act(Action(type="click", x=100, y=100))
    assert env.check(task) is Status.RUNNING

    env.act(Action(type="click", x=400, y=300))
    assert env.check(task) is Status.SUCCESS


def test_parse_action_variants():
    assert parse_action('{"type": "click", "x": 10, "y": 20}').describe() == "click(10,20)"
    assert parse_action('废话 {"type":"key","key":"space"} 后缀').describe() == "key(space)"
    assert parse_action('{"type":"wait","ms":250}').describe() == "wait(250ms)"
    # 坐标越界裁剪
    a = parse_action('{"type":"click","x":9999,"y":-5}', screen_size=(800, 600))
    assert (a.x, a.y) == (799, 0)

    with pytest.raises(ActionParseError):
        parse_action("没有任何json")
    with pytest.raises(ActionParseError):
        parse_action('{"type":"fly"}')


def test_runner_full_loop_with_scripted_decider():
    """最小闭环验证：capture → prompt → decide → act → check → 循环终止。"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    received_prompts: list[str] = []

    async def scripted_decider(prompt: str, screenshot: bytes) -> str:
        """模拟一个"完美的多模态LLM"：直接输出命中靶心的动作。
        同时校验管道确实把 prompt 和截图喂了进来。"""
        assert prompt and "任务目标" in prompt
        assert screenshot[:4] == b"\x89PNG"
        received_prompts.append(prompt)
        return json.dumps({"type": "click", "x": 500, "y": 200})

    runner = AgentRunner(env=env, decider=scripted_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=10)))

    assert result.status is Status.SUCCESS
    assert result.steps == 1
    assert len(received_prompts) == 1


def test_runner_survives_garbage_then_converges():
    """管道可靠性：LLM 前两次输出垃圾（触发重试反馈环），第三次命中。"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    calls = {"n": 0}

    async def flaky_decider(prompt: str, screenshot: bytes) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "我觉得应该点中间附近"                      # 无 JSON → 触发重试
        if calls["n"] == 2:
            return '{"type": "teleport", "x": 1, "y": 1}'      # 非法动作 → 触发重试
        if calls["n"] == 3:
            # 第3次调用 = 第1步内的首次重试，错误反馈必须已注入
            assert "上一次输出无效" in prompt
        # 第2步起为正常调用，prompt 本就不应带反馈
        return json.dumps({"type": "click", "x": 500, "y": 200})

    runner = AgentRunner(env=env, decider=flaky_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=10)))

    assert result.status is Status.SUCCESS
    assert calls["n"] == 3


def test_runner_fail_on_timeout():
    env = MockEnv(seed=1)
    env.set_target(500, 200)

    async def stubborn_decider(prompt: str, screenshot: bytes) -> str:
        return json.dumps({"type": "click", "x": 10, "y": 10})

    runner = AgentRunner(env=env, decider=stubborn_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))

    assert result.status is Status.FAIL
    assert result.steps == 5


def test_step_feedback_injected_on_second_step():
    """僵死循环修复：第一步未命中时，第二步 prompt 必须带显式反馈"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    prompts: list[str] = []

    async def decider(prompt: str, screenshot: bytes) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return json.dumps({"type": "click", "x": 10, "y": 10})   # 脱靶
        return json.dumps({"type": "click", "x": 500, "y": 200})     # 命中

    runner = AgentRunner(env=env, decider=decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=10)))

    assert result.status is Status.SUCCESS
    assert result.steps == 2
    assert "# 上一步反馈" not in prompts[0]      # 第一步无反馈
    assert "# 上一步反馈" in prompts[1]           # 第二步有反馈
    assert "click(10,10)" in prompts[1]           # 反馈包含上一步动作
    assert "不要原样重复" in prompts[1]


def test_mock_env_notes_explain_red_dots():
    """红点说明进 notes：让多模态通道知道红点是自己落的、白块才是目标"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)

    assert env.capture().notes == ""               # 未点击前无说明
    env.act(Action(type="click", x=10, y=10))
    assert "红点" in env.capture().notes           # 点击后出现红点说明
