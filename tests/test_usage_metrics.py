"""Runner 与 trace 的 usage 采集测试。"""
import pytest

from game_agent.framework import AgentRunner, MockEnv, RunTraceLogger, Task


@pytest.mark.asyncio
async def test_runner_accumulates_usage_and_trace_records_it(tmp_path):
    calls = {"n": 0}

    async def decider(prompt: str, images: list[bytes]) -> str:
        calls["n"] += 1
        decider.last_usage = {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_eval_ms": 10.0,
            "eval_ms": 5.0,
            "total_ms": 20.0,
            "done_reason": "length" if calls["n"] == 1 else "stop",
        }
        decider.last_thinking = "先看棋盘，再判断"
        return '{"type": "wait"}'

    decider.last_usage = None
    decider.last_thinking = ""
    tracer = RunTraceLogger(log_path=tmp_path / "trace.md")
    runner = AgentRunner(
        env=MockEnv(seed=1),
        decider=decider,
        step_interval_s=0,
        trace_logger=tracer,
    )
    result = await runner.run(Task(goal="测试", timeout_steps=2))

    assert result.usage["calls"] == 2
    assert result.usage["prompt_tokens"] == 200
    assert result.usage["completion_tokens"] == 40
    assert result.usage["prompt_eval_ms"] == 20.0
    assert result.usage["eval_ms"] == 10.0
    assert result.usage["max_seq"] == 120
    assert result.usage["max_prompt_tokens"] == 100
    assert result.usage["max_completion_tokens"] == 20
    assert result.usage["length_stops"] == 1

    text = (tmp_path / "trace.md").read_text(encoding="utf-8")
    assert "Token 用量" in text
    assert "序列=120" in text
    assert "生成结束原因" in text
    assert "模型思考过程" in text
    assert "先看棋盘，再判断" in text
    assert "上下文峰值" in text
    assert "截断次数" in text
    assert "Token 合计" in text
