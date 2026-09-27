"""真实 LLM 微型基准测试：MockEnv + Ollama 多模态模型，跑 N 次并输出统计。

这是框架的第一个 benchmark：
- 固定种子考题：第 i 次运行的靶位永远一致 → 结果可复现
- 统计命中率 / 平均步数 / 解析错误率 / 平均耗时
- --save 保存 markdown 结果（基线留档，供后续对比）

前置：ollama serve 在运行，且已 pull 多模态模型（默认 qwen2.5vl:7b）。
用法：
    python scripts/run_mock_llm.py --runs 3            # 先跑 3 次试水
    python scripts/run_mock_llm.py --runs 10 --save    # 正式基线，留档

注意：本地 LLM 每步一次推理，10 次运行可能耗时 10-60 分钟。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config.settings import AppSettings
from src.framework import AgentRunner, MockEnv, Task, make_llm_decider
from src.framework.types import ActionParseError, Status
from src.llm.ollama_client import OllamaClient

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "benchmark_results"


@dataclass
class RunRecord:
    index: int
    target: tuple[int, int]
    status: str  # success / fail / parse_error
    steps: int | None  # None = 因解析错误中止，步数未知
    seconds: float
    actions: list[str]


async def run_once(decider, run_index: int, steps_limit: int) -> RunRecord:
    """单次运行。seed=run_index → 第 i 次靶位固定（考题锁定，可复现）。"""
    env = MockEnv(seed=run_index)
    runner = AgentRunner(
        env=env,
        decider=decider,
        step_interval_s=0.2,
        parse_retries=3,
    )
    task = Task(goal="点击画面中的白色方块", timeout_steps=steps_limit)

    t0 = time.perf_counter()
    try:
        result = await runner.run(task)
    except ActionParseError:
        return RunRecord(run_index, env.target, "parse_error", None,
                         time.perf_counter() - t0, [])

    seconds = time.perf_counter() - t0
    status = "success" if result.status is Status.SUCCESS else "fail"
    return RunRecord(run_index, env.target, status, result.steps, seconds,
                     [a.describe() for a in result.actions])


async def amain(args: argparse.Namespace) -> tuple[list[RunRecord], str]:
    settings = AppSettings()
    client = OllamaClient(settings)
    if args.model:
        client.model = args.model
    decider = make_llm_decider(client)

    print(f"模型: {client.model} | 次数: {args.runs} | 最大步数: {args.steps}")
    print("提示：每步一次 LLM 推理，速度取决于本地硬件；Ctrl+C 放弃本次统计\n")

    records: list[RunRecord] = []
    for i in range(1, args.runs + 1):
        try:
            rec = await run_once(decider, i, args.steps)
        except Exception as e:
            print(f"[run {i:>2}/{args.runs}] 异常中断: {e}")
            if i == 1:
                print("提示：请确认 `ollama serve` 在运行，且已 `ollama pull` 对应多模态模型")
            break
        records.append(rec)
        steps_s = str(rec.steps) if rec.steps is not None else "-"
        print(f"[run {i:>2}/{args.runs}] {rec.status:<11} 步数={steps_s:>3} "
              f"耗时={rec.seconds:5.1f}s 靶位={rec.target}")
    return records, client.model


def build_summary(records: list[RunRecord], model_name: str, steps_limit: int) -> str:
    n = len(records)
    succ = sum(1 for r in records if r.status == "success")
    perr = sum(1 for r in records if r.status == "parse_error")
    steps = [r.steps for r in records if r.steps is not None]
    avg_steps = f"{sum(steps) / len(steps):.1f}" if steps else "-"
    avg_time = sum(r.seconds for r in records) / n
    return "\n".join([
        "=" * 56,
        f"汇总  模型={model_name}  n={n}  最大步数={steps_limit}",
        f"命中率:     {succ}/{n} = {succ / n:6.1%}",
        f"平均步数:   {avg_steps}（仅计自然结束的运行）",
        f"解析错误率: {perr}/{n} = {perr / n:6.1%}",
        f"平均耗时:   {avg_time:.1f}s/次",
        "=" * 56,
    ])


def build_run_table(records: list[RunRecord]) -> str:
    lines = ["| run | 靶位 | 结果 | 步数 | 耗时s | 动作序列 |",
             "|---|---|---|---|---|---|"]
    for r in records:
        actions = " → ".join(r.actions) if r.actions else "-"
        steps = r.steps if r.steps is not None else "-"
        lines.append(f"| {r.index} | {r.target[0]},{r.target[1]} | {r.status} "
                     f"| {steps} | {r.seconds:.1f} | {actions} |")
    return "\n".join(lines)


def save_markdown(records: list[RunRecord], args: argparse.Namespace,
                  model_name: str, summary: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"baseline_{model_name.replace(':', '_')}_{ts}.md"
    content = (
        f"# MockEnv 基线记录\n\n"
        f"- 模型: `{model_name}`\n"
        f"- 日期: {datetime.now().isoformat(timespec='seconds')}\n"
        f"- 任务: 点击白色方块（固定种子，第 i 次靶位可复现）\n"
        f"- 运行次数: {args.runs}  最大步数: {args.steps}\n\n"
        f"```\n{summary}\n```\n\n"
        f"## 每次运行明细\n\n{build_run_table(records)}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MockEnv + Ollama 微型基准测试")
    p.add_argument("--runs", type=int, default=5, help="运行次数（默认 5）")
    p.add_argument("--steps", type=int, default=15,
                   help="每次最大步数，超时判 FAIL（默认 15）")
    p.add_argument("--model", type=str, default=None,
                   help="覆盖 OLLAMA_MODEL 环境变量")
    p.add_argument("--save", action="store_true",
                   help="保存结果 markdown 到 benchmark_results/")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    records, model_name = asyncio.run(amain(args))
    if not records:
        print("没有完成的运行，无统计。")
        return
    summary = build_summary(records, model_name, args.steps)
    print("\n" + summary)
    if args.save:
        path = save_markdown(records, args, model_name, summary)
        print(f"已保存: {path}")


if __name__ == "__main__":
    main()
