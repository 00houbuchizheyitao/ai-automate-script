"""VirtualMinesweeperEnv 测试：无头渲染 + 事件注入（零桌面干扰，可 CI）。

确定性保证：固定 seed → 雷位固定；首击必安全 → 点击非雷格序列必然不踩雷。
"""
import asyncio
import json

import pytest

from src.framework import Action, AgentRunner, Status, Task, VirtualMinesweeperEnv


@pytest.fixture(scope="module")
def mines():
    """seed=42 的原始雷位（与虚拟环境内的 Game 同种子同布局）"""
    from minesweeper import Game
    return Game(42).mines


def _center(cell):
    return (cell[0] * 40 + 20, cell[1] * 40 + 20)


def _id(cell):
    return str(cell[1] * 9 + cell[0] + 1)


def test_fresh_board_has_81_tags():
    env = VirtualMinesweeperEnv(seed=42)
    frame = env.capture()
    assert len(frame.tags) == 81
    assert frame.annotated and frame.annotated[:4] == b"\x89PNG"
    assert frame.tags["1"] == (20, 20)          # 无外框偏移，纯棋盘坐标
    assert "SoM" in frame.notes


def test_first_click_safe_then_progress():
    """首击必安全：点击 (0,0) 后不可能 LOSE，且该格从编号图中消失"""
    env = VirtualMinesweeperEnv(seed=42)
    task = Task(goal="g", timeout_steps=20, meta={"safe_opens": 30})  # 高目标防提前SUCCESS

    env.act(Action(type="click", x=20, y=20))   # 格 (0,0)
    assert env.check(task) is not Status.FAIL
    assert "1" not in env.capture().tags        # 已翻开的格子从编号图中消失


def test_click_known_mine_loses(mines):
    """先翻一个安全格，再点已知雷位 → LOSE（判定链路验证）"""
    env = VirtualMinesweeperEnv(seed=42)
    task = Task(goal="g", timeout_steps=20, meta={"safe_opens": 30})

    safe = next((c, r) for r in range(9) for c in range(9) if (c, r) not in mines)
    env.act(Action(type="click", x=_center(safe)[0], y=_center(safe)[1]))
    assert env.check(task) is not Status.FAIL   # 安全格 → 未判负

    mine = next(iter(mines))
    env.act(Action(type="click", x=_center(mine)[0], y=_center(mine)[1]))
    assert env.check(task) is Status.FAIL       # 踩雷 → FAIL


def test_reset_restores_fresh_board(mines):
    """reset 直接重建同种子 Game：确定性复现原始局面"""
    env = VirtualMinesweeperEnv(seed=42)
    safe = next((c, r) for r in range(9) for c in range(9) if (c, r) not in mines)
    env.act(Action(type="click", x=_center(safe)[0], y=_center(safe)[1]))
    assert len(env.capture().tags) < 81
    env.reset()
    assert len(env.capture().tags) == 81


def test_full_loop_with_id_clicks(mines):
    """端到端：LLM 只报编号（无坐标），Runner 解析后翻满 3 个安全格。

    策略固定选"编号列表中第一个非雷格"——雷位已知且首击非雷（无重定位），
    全程确定性。
    """
    env = VirtualMinesweeperEnv(seed=42)
    clicked: list[int] = []

    async def decider(prompt: str, images: list[bytes]) -> str:
        line = next(l for l in prompt.splitlines() if l and l[0].isdigit())
        ids = [int(s.strip()) for s in line.split(",")]
        pick = next(i for i in ids if ((i - 1) % 9, (i - 1) // 9) not in mines)
        clicked.append(pick)
        return json.dumps({"type": "click", "id": str(pick)})

    runner = AgentRunner(env=env, decider=decider, step_interval_s=0)
    result = asyncio.run(runner.run(
        Task(goal="g", timeout_steps=15, meta={"safe_opens": 3})))

    assert result.status is Status.SUCCESS
    assert len(clicked) >= 3
