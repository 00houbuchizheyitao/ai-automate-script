"""首个真实游戏考题：在扫雷里安全翻开 3 格，不踩雷。

前置：
    1. pip 依赖已装（pygame/pyautogui/pygetwindow 在 requirements 里）
    2. 另开一个终端启动游戏并保持窗口可见（不要最小化）：
       python minesweeper.py 42
    3. 本脚本运行期间不要移动鼠标/键盘（pyautogui 注入的是真实输入）

跑法：
    python scripts/run_minesweeper.py            # 真实 LLM 一次运行
    python scripts/run_minesweeper.py --dry-run  # 只看感知与判定，不动鼠标
    python scripts/run_minesweeper.py --env virtual --runs 20 --parallel 8 --full-game --fc
                                                 # 跑 20 局、最多 8 局并发，报告写入 run_trace_multi/
"""
from __future__ import annotations

import argparse
import asyncio
import math
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game_agent.config.settings import AppSettings
from game_agent.framework import (
    AgentRunner,
    MinesweeperEnv,
    RunTraceLogger,
    Task,
    make_llm_decider,
)
from game_agent.framework.types import ActionParseError, Status
from game_agent.llm import OnlineLLMClient, create_llm_client

_GOAL_SUFFIX = (
    "发给你的两张图一张是原图一张是序号图，你根据原图分析局面，决定应该翻开哪个格子，"
    "序号图告诉你每个格子对应的序号，在格子中间，你想翻开某个或多个格子只要报出序号就行，"
    "标记地雷格也是一样，有橙色三角形标记的格子就是你标记出来有雷的格子。")

GOAL = "这是扫雷游戏，你的目标是根据当前局面分析下一步翻开哪个格子是安全的。" + _GOAL_SUFFIX

# 9×9 棋盘共 81 格，其中 10 颗雷 → 71 个安全格
FULL_GAME_SAFE_OPENS = 71

BASE_DIR = Path(__file__).resolve().parent.parent
MULTI_TRACE_DIR = BASE_DIR / "llm_views" / "run_trace_multi"
BENCHMARK_DIR = BASE_DIR / "benchmark_results"


@dataclass
class ParallelRun:
    """并行测试中单局的汇总记录。"""
    index: int
    seed: int
    model: str
    status: str
    steps: int | None
    actions: int
    elapsed_s: float
    usage: dict
    trace_path: Path
    error: str = ""


def _resolve_task_config(args: argparse.Namespace) -> tuple[int, int]:
    """返回 (safe_opens, timeout_steps)。--full-game 优先于 --safe-opens。"""
    if args.full_game:
        steps = args.steps if args.steps is not None else 120
        return FULL_GAME_SAFE_OPENS, steps
    safe_opens = args.safe_opens if args.safe_opens is not None else 3
    steps = args.steps if args.steps is not None else 10
    return safe_opens, steps


def _build_task(args: argparse.Namespace) -> Task:
    safe_opens, steps = _resolve_task_config(args)
    return Task(goal=GOAL, timeout_steps=steps, meta={"safe_opens": safe_opens})


def _create_decider(args: argparse.Namespace, run_label: str | None = None):
    """创建独立的 LLM 客户端与 decider。

    并行时必须每局独立客户端：last_usage / last_thinking 是实例状态，
    共享实例会让不同 run 互相覆盖用量与思考过程。
    """
    settings = AppSettings()
    prefix = f"[{run_label}] " if run_label else ""

    if args.llm == "online":
        def on_progress(n: int) -> None:
            print(f"{prefix}仍在思考，已接收 {n} 字符", flush=True)

        client = create_llm_client(settings, provider="online", model=args.model,
                                   function_calling=args.fc,
                                   progress_callback=on_progress)
    else:
        client = create_llm_client(settings, provider="ollama", model=args.model,
                                   function_calling=args.fc)
    return client, make_llm_decider(client)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return path.as_posix()


async def _run_one_parallel(args: argparse.Namespace, index: int, seed: int) -> ParallelRun:
    """并行执行一局；异常收敛到 ParallelRun，避免单局失败取消其他 run。"""
    from game_agent.framework import VirtualMinesweeperEnv

    trace_path = MULTI_TRACE_DIR / f"run_{index}_seed_{seed}" / "run_trace.md"
    t0 = time.perf_counter()
    model = "?"
    calls = 0
    try:
        client, decider = _create_decider(args, run_label=f"run {index}")
        model = client.model

        async def counting_decider(prompt: str, images: list[bytes]) -> str:
            """统计真实 LLM 调用次数（在线客户端不返回 usage.calls）。"""
            nonlocal calls
            calls += 1
            try:
                return await decider(prompt, images)
            finally:
                counting_decider.last_usage = getattr(decider, "last_usage", None)
                counting_decider.last_thinking = getattr(decider, "last_thinking", "")

        counting_decider.last_usage = None
        counting_decider.last_thinking = ""

        env = VirtualMinesweeperEnv(seed=seed)
        task = _build_task(args)
        tracer = RunTraceLogger(log_path=trace_path)

        def on_step(step: int, subs: list, status: Status) -> None:
            desc = ", ".join(a.describe() for a in subs) or "(无动作)"
            print(f"[run {index}][步 {step}] {desc} → {status.value}", flush=True)

        runner = AgentRunner(env=env, decider=counting_decider,
                             step_interval_s=0.2, parse_retries=3,
                             trace_logger=tracer, on_step=on_step,
                             include_action_options=not args.fc)
        result = await runner.run(task)
        usage = dict(result.usage)
        usage["calls"] = calls
        return ParallelRun(index=index, seed=seed, model=model,
                           status=result.status.value, steps=result.steps,
                           actions=len(result.actions),
                           elapsed_s=time.perf_counter() - t0,
                           usage=usage, trace_path=trace_path)
    except ActionParseError as e:
        return ParallelRun(index=index, seed=seed, model=model,
                           status="parse_error", steps=None, actions=0,
                           elapsed_s=time.perf_counter() - t0,
                           usage={"calls": calls},
                           trace_path=trace_path,
                           error=f"ActionParseError: {e}")
    except Exception as e:
        return ParallelRun(index=index, seed=seed, model=model,
                           status="error", steps=None, actions=0,
                           elapsed_s=time.perf_counter() - t0,
                           usage={"calls": calls},
                           trace_path=trace_path,
                           error=f"{type(e).__name__}: {e}")


def _p95(values: list[int]) -> str:
    if not values:
        return "-"
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return str(ordered[index])


def _build_parallel_summary(args: argparse.Namespace,
                            results: list[ParallelRun]) -> str:
    safe_opens, max_steps = _resolve_task_config(args)
    settings = AppSettings()
    n = len(results)
    success = sum(1 for r in results if r.status == "success")
    parse_errors = sum(1 for r in results if r.status == "parse_error")
    finished = [r for r in results if r.steps is not None]
    avg_steps = (f"{sum(r.steps for r in finished) / len(finished):.1f}"
                 if finished else "-")
    p95_steps = _p95([r.steps for r in finished if r.steps is not None])
    avg_time = sum(r.elapsed_s for r in results) / n if n else 0.0
    prompt_tokens = sum(int(r.usage.get("prompt_tokens", 0)) for r in results)
    completion_tokens = sum(int(r.usage.get("completion_tokens", 0)) for r in results)
    calls = sum(int(r.usage.get("calls", 0)) for r in results)
    length_stops = sum(int(r.usage.get("length_stops", 0)) for r in results)
    model = next((r.model for r in results if r.model != "?"), "?")
    if args.llm == "ollama":
        sampling = (f"temperature={settings.OLLAMA_TEMPERATURE}, "
                    f"top_p={settings.OLLAMA_TOP_P}, thinking={settings.OLLAMA_THINK}")
    else:
        sampling = (f"thinking={settings.ONLINE_THINKING}, "
                    f"max_tokens={settings.ONLINE_MAX_TOKENS}（温度由服务端决定）")
    task_desc = (f"完整局（safe_opens={safe_opens}）" if args.full_game
                 else f"安全翻开 {safe_opens} 格")
    lines = [
        "# 并行运行汇总",
        "",
        f"- 模型: `{model}`",
        f"- 后端: {args.llm} | {sampling}",
        f"- 时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 并行上限: {args.parallel} | 总局数: {n} | 种子: {args.seed}..{args.seed + n - 1}",
        f"- 任务: {task_desc} | 最大步数: {max_steps}",
        f"- 动作协议: {'function calling' if args.fc else 'prompt JSON'}",
        "",
        "| run | seed | 结果 | 步数 | 动作数 | 调用 | 耗时s | prompt | completion | 截断 | trace |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        steps = r.steps if r.steps is not None else "-"
        lines.append(
            f"| {r.index} | {r.seed} | {r.status} | {steps} | {r.actions} "
            f"| {int(r.usage.get('calls', 0))} | {r.elapsed_s:.1f} "
            f"| {int(r.usage.get('prompt_tokens', 0))} "
            f"| {int(r.usage.get('completion_tokens', 0))} "
            f"| {int(r.usage.get('length_stops', 0))} | {_display_path(r.trace_path)} |")
    lines += [
        "",
        f"**成功率**: {success}/{n} = {(success / n if n else 0):.1%}",
        f"**平均步数**: {avg_steps}（仅计自然结束的运行）",
        f"**P95 步数**: {p95_steps}",
        f"**解析错误率**: {parse_errors}/{n} = {(parse_errors / n if n else 0):.1%}",
        f"**平均耗时**: {avg_time:.1f}s/次",
        f"**平均调用次数**: {(calls / n if n else 0):.1f}",
        f"**Token 合计**: prompt={prompt_tokens} completion={completion_tokens}",
        f"**截断次数**: {length_stops} 次 done_reason=length",
    ]
    errors = [r for r in results if r.error]
    if errors:
        lines += ["", "## 错误", ""]
        lines += [f"- run {r.index} (seed={r.seed}): {r.error}" for r in errors]
    return "\n".join(lines)


async def _run_parallel(args: argparse.Namespace) -> int:
    """并行跑 n 局：每局独立 seed、独立客户端、独立 trace 目录。"""
    if MULTI_TRACE_DIR.exists():
        shutil.rmtree(MULTI_TRACE_DIR)
    MULTI_TRACE_DIR.mkdir(parents=True, exist_ok=True)

    total = args.runs if args.runs is not None else args.parallel
    seeds = [args.seed + i for i in range(total)]
    print(f"并行上限: {args.parallel} | 总局数: {total} | 种子 {seeds[0]}..{seeds[-1]}")
    print(f"报告目录: {MULTI_TRACE_DIR}")
    print("提示：并发请求会受后端排队/限流影响，实际加速取决于服务端\n")

    sem = asyncio.Semaphore(args.parallel)

    async def run_one(index: int, seed: int) -> ParallelRun:
        async with sem:
            return await _run_one_parallel(args, index, seed)

    results = await asyncio.gather(*[
        run_one(i + 1, seed) for i, seed in enumerate(seeds)
    ])
    results.sort(key=lambda r: r.index)

    summary = _build_parallel_summary(args, results)
    print("\n" + summary)
    summary_path = MULTI_TRACE_DIR / "summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"\n汇总已保存: {summary_path}")

    if args.save:
        model = next((r.model for r in results if r.model != "?"), "?")
        protocol = "fc" if args.fc else "prompt-json"
        model_slug = model.replace(":", "_").replace("/", "_")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
        baseline_path = BENCHMARK_DIR / f"baseline_{model_slug}_{protocol}_{ts}.md"
        baseline_path.write_text(summary, encoding="utf-8")
        print(f"基线已归档: {baseline_path}")
    return 0 if all(r.status == "success" for r in results) else 1


async def amain(args: argparse.Namespace) -> int:
    total_runs = args.runs if args.runs is not None else args.parallel
    if total_runs > 1 or args.parallel > 1:
        return await _run_parallel(args)

    if args.env == "virtual":
        from game_agent.framework import VirtualMinesweeperEnv
        env = VirtualMinesweeperEnv(seed=args.seed)
        print(f"无头模式：游戏在进程内运行（seed={args.seed}），不占用桌面")
    else:
        env = MinesweeperEnv()
        print(f"窗口定位: title={env.window_title!r} region={env._resolve_region()}")
    if args.full_game:
        safe_opens, steps = _resolve_task_config(args)
        print(f"模式: 完整局（safe_opens={safe_opens}, 最大步数={steps}）")
    task = _build_task(args)

    if args.dry_run:
        frame = env.capture()
        print(f"感知元素 {len(frame.elements)} 个:")
        for e in frame.elements[:15]:
            print(f"  {e.text!r} @ ({e.x},{e.y}) conf={e.confidence:.2f}")
        print(f"check 判定: {env.check(task).value}")
        print("（dry-run 结束，未注入任何键鼠输入）")
        return 0

    if args.llm == "human":
        # 审查模式：定位窗口 → 截图 + SoM → 生成"将发给 LLM 的完整信息"→ 结束。
        # 图像经与在线客户端相同的重编码，保证人看到的 = LLM 看到的。
        from game_agent.framework.human_decider import dump_llm_view
        md = dump_llm_view(env, task, out_dir="llm_views",
                           normalizer=OnlineLLMClient._normalize_image)
        print(f"LLM 视角信息已生成: {md}")
        print("请在 IDE 中审查：第一张图 = 原始画面，第二张图 = SoM 编号标注图，"
              "prompt 为将要发送的完整文本（一字不差）。")
        print("确认信息质量后，用 --llm online 跑真实闭环。")
        return 0
    client, decider = _create_decider(args)
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
    if result.usage and result.usage.get("calls"):
        u = result.usage
        print(f"Token: prompt={u.get('prompt_tokens', 0)}, "
              f"completion={u.get('completion_tokens', 0)}, "
              f"调用={u.get('calls', 0)} 次")
        print(f"模型耗时: prompt_eval={float(u.get('prompt_eval_ms', 0)) / 1000:.2f}s, "
              f"eval={float(u.get('eval_ms', 0)) / 1000:.2f}s")
        print(f"上下文峰值: {u.get('max_seq', 0)} tokens "
              f"(prompt max={u.get('max_prompt_tokens', 0)}, "
              f"completion max={u.get('max_completion_tokens', 0)})")
        if u.get("length_stops"):
            print(f"截断: {u['length_stops']} 次 done_reason=length"
                  f"（检查 num_ctx / num_predict）")
    if result.status is Status.SUCCESS:
        print("真实窗口闭环打通 ✓")
        return 0
    print("未达标——追踪日志里有每步的 prompt/原始输出，这就是下一轮改进的素材")
    return 1


def main() -> None:
    p = argparse.ArgumentParser(description="扫雷首个真实游戏考题")
    p.add_argument("--full-game", action="store_true",
                   help="完整局模式：自动设置 safe_opens=71、默认步数=120；"
                        "任务提示词与普通模式相同（优先于 --safe-opens）")
    p.add_argument("--safe-opens", type=int, default=None,
                   help="需安全翻开的格子数（默认 3；--full-game 时为 71）")
    p.add_argument("--steps", type=int, default=None,
                   help="最大步数（默认 10；--full-game 时为 120）")
    p.add_argument("--parallel", type=int, default=1,
                   help="并发上限（默认 1）。多局时每局独立 trace 写入 "
                        "llm_views/run_trace_multi/run_<i>_seed_<seed>/；"
                        "仅支持 --env virtual，且不支持 --llm human / --dry-run")
    p.add_argument("--runs", type=int, default=None,
                   help="总测试局数（默认等于 --parallel）；--runs 20 --parallel 8 "
                        "表示跑 20 局、最多 8 局同时进行")
    p.add_argument("--env", choices=("window", "virtual"), default="window",
                   help="window = 真实游戏窗口（扮演模式/dry-run 用）；"
                        "virtual = 无头进程内运行（零桌面干扰，无需启动游戏）")
    p.add_argument("--seed", type=int, default=42,
                   help="virtual 模式的起始雷位种子（并行时逐局 +1）")
    p.add_argument("--llm", choices=("ollama", "online", "human"), default="ollama",
                   help="模型后端：online = GLM 等在线 API；human = 审查模式"
                        "（定位窗口→截图+SoM→生成将发给 LLM 的 md→结束，不调用模型）")
    p.add_argument("--model", type=str, default=None,
                   help="覆盖模型名（ollama: OLLAMA_MODEL / online: ONLINE_MODEL）")
    p.add_argument("--fc", action="store_true",
                   help="启用 Function Calling（online / ollama）：动作由 API 层 "
                        "tools schema 声明，prompt 省略 JSON 写法——可与默认的 "
                        "prompt-json 模式做 A/B 对比；Ollama 需模型支持 tools")
    p.add_argument("--dry-run", action="store_true",
                   help="只跑感知与判定，不注入键鼠（验证窗口定位/OCR）")
    p.add_argument("--save", action="store_true",
                   help="多局跑分时把 summary.md 归档到 benchmark_results/")
    args = p.parse_args()
    if args.fc and args.llm == "human":
        p.error("--fc 不能与 --llm human 一起使用")
    if args.parallel < 1:
        p.error("--parallel 必须 >= 1")
    if args.runs is not None and args.runs < 1:
        p.error("--runs 必须 >= 1")
    total_runs = args.runs if args.runs is not None else args.parallel
    multi_run = total_runs > 1 or args.parallel > 1
    if multi_run:
        if args.env != "virtual":
            p.error("多局跑分仅支持 --env virtual（窗口模式共享同一桌面和键鼠）")
        if args.llm == "human":
            p.error("多局跑分不支持 --llm human")
        if args.dry_run:
            p.error("多局跑分不支持 --dry-run")
    if args.save and not multi_run:
        p.error("--save 仅用于多局跑分")

    raise SystemExit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
