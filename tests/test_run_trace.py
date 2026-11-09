"""RunTraceLogger 测试：markdown 追加、图片落盘、重试同步分组、结论记录"""
import asyncio

from src.framework import MockEnv, RunTraceLogger, Task


def _read(tmp_path):
    return (tmp_path / "run_trace.md").read_text(encoding="utf-8")


def test_trace_single_step_markdown(tmp_path):
    """一步：md 含原图/SoM图/发给LLM的信息/LLM返回的信息四个区块"""
    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    tracer.log_step(step=1, prompt="第一步prompt", images=[b"\x89PNG-a", b"\x89PNG-b"],
                    raw_output='{"type":"click","id":"5"}',
                    parsed=["click(100,100)"], status="parsed",
                    conclusions=["雷在8或26"], elapsed_s=12.4)

    md = _read(tmp_path)
    assert "## 第 1 步 · 尝试 1" in md
    assert "### 原图" in md and "### SoM 序号图 1" in md
    assert "### 发给 LLM 的信息" in md and "第一步prompt" in md
    assert "### LLM 返回的信息" in md and '{"type":"click","id":"5"}' in md
    assert "**解析动作**：click(100,100)" in md
    assert "**执行后状态**：parsed" in md
    assert "**本步耗时**：12.4 秒" in md
    assert "- 雷在8或26" in md
    assert (tmp_path / "trace_step1_try1_img1.png").read_bytes() == b"\x89PNG-a"
    assert (tmp_path / "trace_step1_try1_img2.png").read_bytes() == b"\x89PNG-b"


def test_trace_retry_grouped_under_same_step(tmp_path):
    """解析失败的重试记录为同一步的'尝试 2'，且原图/SoM图两次都落盘"""
    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    tracer.log_step(step=2, prompt="第一次prompt", images=[b"\x89PNG-1"],
                    raw_output="{34, 42, 52}", parsed=None,
                    status="parse_error: JSON 解析失败", conclusions=[])
    tracer.log_step(step=2, prompt="第二次prompt（含错误反馈）", images=[b"\x89PNG-2"],
                    raw_output='{"type":"click","id":"1"}',
                    parsed=["click(20,20)"], status="parsed", conclusions=[])

    md = _read(tmp_path)
    assert "## 第 2 步 · 尝试 1" in md and "## 第 2 步 · 尝试 2" in md
    assert "{34, 42, 52}" in md                        # 失败的原始输出保留
    assert "（解析失败，见上方返回信息）" in md
    assert "trace_step2_try1_img1.png" in md and "trace_step2_try2_img1.png" in md


def test_trace_fresh_start_clears_previous_run(tmp_path):
    """同一 trace 路径再次实例化：旧 md 与旧截图清空，本轮从第 1 步重新开始"""
    log = tmp_path / "run_trace" / "run_trace.md"
    t1 = RunTraceLogger(log_path=log)
    t1.log_step(step=1, prompt="上一轮的prompt", images=[b"\x89PNG-old"],
                raw_output="old output", parsed=[], status="parsed", conclusions=[])
    assert (tmp_path / "run_trace" / "trace_step1_try1_img1.png").exists()

    t2 = RunTraceLogger(log_path=log)  # 模拟下一次运行：清空重建
    assert not (tmp_path / "run_trace" / "trace_step1_try1_img1.png").exists()
    t2.log_step(step=1, prompt="新一轮的prompt", images=[], raw_output="new output",
                parsed=[], status="parsed", conclusions=[])

    md = log.read_text(encoding="utf-8")
    assert "新一轮的prompt" in md
    assert "上一轮的prompt" not in md and "old output" not in md


def test_trace_real_png_from_env(tmp_path):
    """真实环境截图落盘验证（MockEnv 产出）"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    frame = env.capture()
    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    paths = tracer.log_step(step=1, prompt="p", images=[frame.screenshot],
                            raw_output="{}", parsed=[], status="parsed",
                            conclusions=[])
    assert (tmp_path / paths[0]).read_bytes() == frame.screenshot


def test_trace_conclusions_omitted_when_empty(tmp_path):
    """无结论时不出现结论区块"""
    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    tracer.log_step(step=1, prompt="p", images=[], raw_output="{}",
                    parsed=[], status="parsed", conclusions=[])
    assert "推理结论" not in _read(tmp_path)


def test_runner_integrates_tracer(tmp_path):
    """Runner 注入 tracer 后，每步信息实时追加到 md"""
    from src.framework import AgentRunner

    env = MockEnv(seed=1)
    env.set_target(500, 200)

    async def decider(prompt: str, images: list) -> str:
        return '{"type": "click", "id": "5"}'  # MockEnv 无 tags → 解析错误重试一次后…

    # MockEnv 无 tags：id 动作会被拒。改用坐标动作保证闭环成功
    calls = {"n": 0}

    async def coord_decider(prompt: str, images: list) -> str:
        calls["n"] += 1
        return '{"type": "click", "x": 500, "y": 200}'

    runner = AgentRunner(env=env, decider=coord_decider, step_interval_s=0,
                         trace_logger=RunTraceLogger(log_path=tmp_path / "run_trace.md"))
    result = asyncio.run(runner.run(Task(goal="g", timeout_steps=5)))

    assert result.status.value == "success"
    md = (tmp_path / "run_trace.md").read_text(encoding="utf-8")
    assert "## 第 1 步" in md and "### LLM 返回的信息" in md


def test_trace_finish_summary(tmp_path):
    """运行结束追加'测试结束'节：结束原因/总步数/动作序列/结论数"""
    from src.framework import Action

    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    tracer.log_finish(
        reason="任务判定结束：fail（第 2 步判定）", steps=2, max_steps=20,
        actions=[Action(type="click", x=180, y=180),
                 Action(type="click", x=180, y=140)],
        conclusions=["结论A", "结论B"])

    md = _read(tmp_path)
    assert "## 测试结束" in md
    assert "任务判定结束：fail（第 2 步判定）" in md
    assert "**总步数**：2（上限 20）" in md
    assert "click(180,180) → click(180,140)" in md
    assert "2 条存入结论记忆" in md


def test_runner_writes_finish_summary(tmp_path):
    """Runner 判定结束后，md 末尾有结束原因节（区分判负与崩溃）"""
    from src.framework import AgentRunner

    env = MockEnv(seed=1)
    env.set_target(500, 200)

    async def decider(prompt: str, images: list) -> str:
        return '{"type": "click", "x": 500, "y": 200}'

    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    runner = AgentRunner(env=env, decider=decider, step_interval_s=0,
                         trace_logger=tracer)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))

    assert result.status.value == "success"
    md = _read(tmp_path)
    assert "## 测试结束" in md
    assert "任务判定结束：success（第 1 步判定）" in md


def test_runner_traces_abort_on_parse_exhaustion(tmp_path):
    """解析重试耗尽抛异常 → md 末尾记'异常中断'（区分崩溃与判负）"""
    import pytest

    from src.framework import ActionParseError, AgentRunner

    env = MockEnv(seed=1)

    async def garbage(prompt: str, images: list) -> str:
        return "这段话里没有json"

    tracer = RunTraceLogger(log_path=tmp_path / "run_trace.md")
    runner = AgentRunner(env=env, decider=garbage, parse_retries=1,
                         trace_logger=tracer)
    with pytest.raises(ActionParseError):
        asyncio.run(runner.run(Task(goal="g", timeout_steps=3)))

    md = _read(tmp_path)
    assert "## 测试结束" in md
    assert "异常中断：ActionParseError" in md
