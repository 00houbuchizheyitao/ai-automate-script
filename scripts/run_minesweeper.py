"""首个真实游戏考题：在扫雷里安全翻开 3 格，不踩雷。

前置：
    1. pip 依赖已装（pygame/pyautogui/pygetwindow 在 requirements 里）
    2. 另开一个终端启动游戏并保持窗口可见（不要最小化）：
       python minesweeper.py 42
    3. 本脚本运行期间不要移动鼠标/键盘（pyautogui 注入的是真实输入）

跑法：
    python scripts/run_minesweeper.py            # 真实 LLM 一次运行
    python scripts/run_minesweeper.py --dry-run  # 只看感知与判定，不动鼠标
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import AppSettings
from src.framework import AgentRunner, MinesweeperEnv, Task, make_llm_decider
from src.framework.types import Status
from src.llm.ollama_client import OllamaClient

GOAL = ("屏幕是一个 9×9 的扫雷棋盘（每格 40 像素，铺满整个窗口），"
        "未翻开的格子是深灰色。用鼠标左键点击翻开格子，首次点击必定安全。"
        "翻开后格子上的数字表示周围 8 格的雷数，根据数字推断哪些格子安全，"
        "翻开 {need} 个安全格子（翻开数字格也算）。不要点击棋盘以外的区域。")


async def amain(args: argparse.Namespace) -> int:
    env = MinesweeperEnv()
    task = Task(goal=GOAL.format(need=args.safe_opens),
                timeout_steps=args.steps,
                meta={"safe_opens": args.safe_opens})

    print(f"窗口定位: title={env.window_title!r} region={env._resolve_region()}")

    if args.dry_run:
        frame = env.capture()
        print(f"感知元素 {len(frame.elements)} 个:")
        for e in frame.elements[:15]:
            print(f"  {e.text!r} @ ({e.x},{e.y}) conf={e.confidence:.2f}")
        print(f"check 判定: {env.check(task).value}")
        print("（dry-run 结束，未注入任何键鼠输入）")
        return 0

    settings = AppSettings()
    runner = AgentRunner(env=env, decider=make_llm_decider(OllamaClient(settings)),
                         step_interval_s=0.2, parse_retries=3)
    result = await runner.run(task)

    print(f"\n结果: {result.status.value}, 用步数: {result.steps}")
    for i, a in enumerate(result.actions, 1):
        print(f"  第{i}步: {a.describe()}")
    if result.status is Status.SUCCESS:
        print("真实窗口闭环打通 ✓")
        return 0
    print("未达标——把动作序列和截图留存，这就是下一轮改进的素材")
    return 1


def main() -> None:
    p = argparse.ArgumentParser(description="扫雷首个真实游戏考题")
    p.add_argument("--safe-opens", type=int, default=3, help="需安全翻开的格子数")
    p.add_argument("--steps", type=int, default=10, help="最大步数")
    p.add_argument("--model", type=str, default=None, help="覆盖 OLLAMA_MODEL")
    p.add_argument("--dry-run", action="store_true",
                   help="只跑感知与判定，不注入键鼠（验证窗口定位/OCR）")
    args = p.parse_args()

    if args.model:
        # 简单覆盖：让 OllamaClient 读到指定模型
        import src.config.settings as s
        s.AppSettings.OLLAMA_MODEL = args.model
    raise SystemExit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
