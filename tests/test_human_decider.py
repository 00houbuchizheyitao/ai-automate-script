"""HumanDecider 测试：markdown 日志内容与图像文件落盘（fake ask，无终端交互）"""
import asyncio

import pytest

from src.framework import HumanDecider, Task


@pytest.mark.asyncio
async def test_dump_llm_view_single_shot(tmp_path):
    """审查模式：一次调用生成 md + 全部附图，prompt 与 Runner 第一步一致，无需交互"""
    from src.framework import MockEnv
    from src.framework.human_decider import dump_llm_view

    env = MockEnv(seed=1)
    env.set_target(500, 200)
    task = Task(goal="点击白色方块", timeout_steps=10)

    md = dump_llm_view(env, task, out_dir=tmp_path)

    assert md.read_text(encoding="utf-8").count("![") == 1   # MockEnv 无标注图 → 单图
    content = (tmp_path / "llm_view.md").read_text(encoding="utf-8")
    assert "点击白色方块" in content                          # prompt 含任务目标
    assert (tmp_path / "llm_view_img1.png").read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_dump_llm_view_includes_annotated_image(tmp_path):
    """带 SoM 标注的帧：两张图都落盘，md 里标注图排第二"""
    from src.framework import MockEnv
    from src.framework.human_decider import dump_llm_view

    class _AnnotatedMock(MockEnv):
        def capture(self):
            frame = super().capture()
            from src.framework.types import FrameAnalysis
            return FrameAnalysis(screenshot=frame.screenshot,
                                 elements=frame.elements, notes=frame.notes,
                                 annotated=frame.screenshot + b"-som")

    env = _AnnotatedMock(seed=1)
    env.set_target(500, 200)
    md = dump_llm_view(env, Task(goal="点击白色方块"), out_dir=tmp_path,
                       normalizer=lambda b: b)

    files = sorted(p.name for p in tmp_path.glob("llm_view_img*.png"))
    assert files == ["llm_view_img1.png", "llm_view_img2.png"]
    content = md.read_text(encoding="utf-8")
    assert content.index("llm_view_img1.png") < content.index("llm_view_img2.png")
    assert "SoM" in content


@pytest.mark.asyncio
async def test_dump_llm_view_applies_normalizer(tmp_path):
    from src.framework import MockEnv
    from src.framework.human_decider import dump_llm_view

    env = MockEnv(seed=1)
    env.set_target(500, 200)
    dump_llm_view(env, Task(goal="g"), out_dir=tmp_path,
                  normalizer=lambda b: b + b"-norm")
    assert (tmp_path / "llm_view_img1.png").read_bytes().endswith(b"-norm")


@pytest.mark.asyncio
async def test_human_decider_logs_prompt_and_image(tmp_path):
    """每次调用：prompt 原文进 md、截图落盘、动作从 ask 读取；
    实例可直接调用（满足 Runner 的 Decider 协议）"""
    log = tmp_path / "llm_view.md"
    inputs = iter(['{"type": "click", "x": 100, "y": 100}',
                   '{"type": "key", "key": "r"}'])
    decider = HumanDecider(log_path=log, ask=lambda _: next(inputs))

    out1 = await decider("第一步的完整prompt文本", [b"\x89PNG-img1"])  # 直接调用实例
    out2 = await decider.decide("第二步prompt（含错误反馈）", [b"\x89PNG-img2"])

    assert out1 == '{"type": "click", "x": 100, "y": 100}'
    assert out2 == '{"type": "key", "key": "r"}'
    assert decider.calls == 2

    md = log.read_text(encoding="utf-8")
    assert "决策调用 1" in md and "决策调用 2" in md
    assert "第一步的完整prompt文本" in md          # prompt 原文一字不差
    assert "第二步prompt（含错误反馈）" in md
    assert "![原始画面]" in md
    assert (tmp_path / "llm_view_call1_img1.png").read_bytes() == b"\x89PNG-img1"
    assert (tmp_path / "llm_view_call2_img1.png").read_bytes() == b"\x89PNG-img2"


@pytest.mark.asyncio
async def test_human_decider_applies_normalizer(tmp_path):
    """normalizer（如在线客户端的 RGB 重编码）应作用于落盘的每张图像"""
    log = tmp_path / "llm_view.md"
    decider = HumanDecider(log_path=log,
                           normalizer=lambda b: b + b"-normalized",
                           ask=lambda _: '{"type": "wait", "ms": 10}')
    await decider.decide("p", [b"raw-", b"raw2-"])
    assert (tmp_path / "llm_view_call1_img1.png").read_bytes() == b"raw--normalized"
    assert (tmp_path / "llm_view_call1_img2.png").read_bytes() == b"raw2--normalized"
