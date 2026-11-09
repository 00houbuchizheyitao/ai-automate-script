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
from src.framework import (
    AgentRunner,
    MinesweeperEnv,
    RunTraceLogger,
    Task,
    make_llm_decider,
)
from src.framework.types import Status
from src.llm.online_client import OnlineLLMClient
from src.llm.ollama_client import OllamaClient

GOAL = ("这是扫雷游戏，你的目标是根据当前局面分析下一步翻开哪个格子是安全的。"
        "发给你的两张图一张是原图一张是序号图，你根据原图分析局面，决定应该翻开哪个格子，"
        "序号图告诉你每个格子对应的序号，在格子中间，你想翻开某个或多个格子只要报出序号就行，"
        "标记地雷格也是一样，有橙色三角形标记的格子就是你标记出来有雷的格子。")


async def amain(args: argparse.Namespace) -> int:
    if args.env == "virtual":
        from src.framework import VirtualMinesweeperEnv
        env = VirtualMinesweeperEnv(seed=args.seed)
        print(f"无头模式：游戏在进程内运行（seed={args.seed}），不占用桌面")
    else:
        env = MinesweeperEnv()
        print(f"窗口定位: title={env.window_title!r} region={env._resolve_region()}")
    task = Task(goal=GOAL,
                timeout_steps=args.steps,
                meta={"safe_opens": args.safe_opens})

    if args.dry_run:
        frame = env.capture()
        print(f"感知元素 {len(frame.elements)} 个:")
        for e in frame.elements[:15]:
            print(f"  {e.text!r} @ ({e.x},{e.y}) conf={e.confidence:.2f}")
        print(f"check 判定: {env.check(task).value}")
        print("（dry-run 结束，未注入任何键鼠输入）")
        return 0

    settings = AppSettings()
    if args.llm == "human":
        # 审查模式：定位窗口 → 截图 + SoM → 生成"将发给 LLM 的完整信息"→ 结束。
        # 图像经与在线客户端相同的重编码，保证人看到的 = LLM 看到的。
        from src.framework.human_decider import dump_llm_view
        md = dump_llm_view(env, task, out_dir="llm_views",
                           normalizer=OnlineLLMClient._normalize_image)
        print(f"LLM 视角信息已生成: {md}")
        print("请在 IDE 中审查：第一张图 = 原始画面，第二张图 = SoM 编号标注图，"
              "prompt 为将要发送的完整文本（一字不差）。")
        print("确认信息质量后，用 --llm online 跑真实闭环。")
        return 0
    if args.llm == "online":
        def on_progress(n: int) -> None:
            # 长思考（实测可达 35 分钟）期间的存活证明：流式仍在收字节
            print(f"  仍在思考，已接收 {n} 字符", flush=True)

        client = OnlineLLMClient(api_key=settings.ONLINE_API_KEY,
                                 model=args.model or settings.ONLINE_MODEL,
                                 base_url=settings.ONLINE_BASE_URL,
                                 timeout=settings.ONLINE_TIMEOUT,
                                 thinking=settings.ONLINE_THINKING,
                                 max_tokens=settings.ONLINE_MAX_TOKENS,
                                 function_calling=args.fc,
                                 progress_callback=on_progress)
        decider = make_llm_decider(client)
    else:
        client = OllamaClient(settings)
        if args.model:
            client.model = args.model
        decider = make_llm_decider(client)
    if args.llm != "human":
        print(f"LLM: {client.model} ({args.llm})")
        print(f"动作协议: {'function calling（tools 硬约束）' if args.fc else 'prompt JSON schema（软约束）'}")
    # 追踪日志：每次 LLM 调用（含重试）实时追加到 md，截图落盘同目录：
    #   Get-Content llm_views\run_trace\run_trace.md -Wait -Tail 30
    tracer = RunTraceLogger(log_path="llm_views/run_trace/run_trace.md")
    print(f"追踪日志: {tracer.log_path}（另开终端 Get-Content -Wait 可实时查看）")

    def on_step(step: int, subs: list, status: Status) -> None:
        desc = ", ".join(a.describe() for a in subs) or "(无动作)"
        print(f"[步 {step}] {desc} → {status.value}", flush=True)

    runner = AgentRunner(env=env, decider=decider,
                         step_interval_s=0.2, parse_retries=3,
                         trace_logger=tracer, on_step=on_step,
                         include_action_options=not args.fc)
    result = await runner.run(task)

    print(f"\n结果: {result.status.value}, 用步数: {result.steps}")
    for i, a in enumerate(result.actions, 1):
        print(f"  第{i}步: {a.describe()}")
    print(f"推理结论 {len(result.conclusions)} 条已存入追踪日志")
    if result.status is Status.SUCCESS:
        print("真实窗口闭环打通 ✓")
        return 0
    print("未达标——追踪日志里有每步的 prompt/原始输出，这就是下一轮改进的素材")
    return 1


def main() -> None:
    p = argparse.ArgumentParser(description="扫雷首个真实游戏考题")
    p.add_argument("--safe-opens", type=int, default=3, help="需安全翻开的格子数")
    p.add_argument("--steps", type=int, default=10, help="最大步数")
    p.add_argument("--env", choices=("window", "virtual"), default="window",
                   help="window = 真实游戏窗口（扮演模式/dry-run 用）；"
                        "virtual = 无头进程内运行（零桌面干扰，无需启动游戏）")
    p.add_argument("--seed", type=int, default=42, help="virtual 模式的雷位种子")
    p.add_argument("--llm", choices=("ollama", "online", "human"), default="ollama",
                   help="模型后端：online = GLM 等在线 API；human = 审查模式"
                        "（定位窗口→截图+SoM→生成将发给 LLM 的 md→结束，不调用模型）")
    p.add_argument("--model", type=str, default=None,
                   help="覆盖模型名（ollama: OLLAMA_MODEL / online: ONLINE_MODEL）")
    p.add_argument("--fc", action="store_true",
                   help="启用 Function Calling（仅 --llm online）：动作由 API 层 "
                        "tools schema 声明，prompt 省略 JSON 写法——可与默认的 "
                        "prompt-json 模式做 A/B 对比")
    p.add_argument("--dry-run", action="store_true",
                   help="只跑感知与判定，不注入键鼠（验证窗口定位/OCR）")
    args = p.parse_args()
    if args.fc and args.llm != "online":
        p.error("--fc 目前仅支持 --llm online（Ollama 的工具调用格式不同，暂未接入）")

    raise SystemExit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
