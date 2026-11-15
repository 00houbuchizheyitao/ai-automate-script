"""运行追踪日志：把真实闭环中每次"发给 LLM 的信息"和"LLM 发回的原始输出"
以人类可读的 markdown 记录（每步一节，运行中实时追加）。

- 与 llm_views/ 一样被 .gitignore 忽略（本地生成，不入库）
- 每次运行清空重建 trace 目录：本轮数据独立完整，不与上次运行混杂
- 每步一节：原图 → SoM 序号图 → 发给 LLM 的信息 → LLM 返回的信息
  （含解析结果、执行状态、推理结论）
- 解析失败的重试调用记录为同一步的"尝试 N"，重试链路完整可见
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path


class RunTraceLogger:
    def __init__(self, log_path: str | Path = "llm_views/run_trace/run_trace.md"):
        self.log_path = Path(log_path)
        self._img_dir = self.log_path.parent
        if self.log_path.exists():
            # 上一次运行的残留 → 清空重来。目录名与日志同名时（约定布局
            # run_trace/run_trace.md）整个目录删掉重建；否则只删日志与旧
            # 截图，防止误删目录内的无关文件
            if self._img_dir.name == self.log_path.stem:
                shutil.rmtree(self._img_dir)
            else:
                self.log_path.unlink()
                for p in self._img_dir.glob("trace_step*_try*_img*.png"):
                    p.unlink()
        self._img_dir.mkdir(parents=True, exist_ok=True)
        self._attempts: dict[int, int] = {}  # 每步的调用计数（重试可见）
        self.log_path.write_text(
            "# 运行追踪\n\n"
            "每步记录：原图、SoM 序号图、发给 LLM 的信息、LLM 返回的信息。\n"
            "（解析失败的重试记录为同一步的'尝试 N'）\n",
            encoding="utf-8")

    def log_step(self, step: int, prompt: str, images: list[bytes],
                 raw_output: str, parsed: list[str] | None,
                 status: str, conclusions: list[str],
                 elapsed_s: float | None = None,
                 usage: dict | None = None,
                 thinking: str = "") -> list[str]:
        """记录一次 LLM 调用。返回本次落盘的图片相对路径列表。

        elapsed_s = 本次尝试的 LLM 调用耗时（秒）；None 时不输出耗时行。
        usage = 模型返回的 token/耗时明细；None 时不输出用量行。
        thinking = thinking 模型的思考过程；空串时不输出该段。
        """
        attempt = self._attempts.get(step, 0) + 1
        self._attempts[step] = attempt
        self._seq = f"{step}.{attempt}"

        img_rel_paths: list[str] = []
        for k, raw in enumerate(images, 1):
            p = self._img_dir / f"trace_step{step}_try{attempt}_img{k}.png"
            p.write_bytes(raw)
            img_rel_paths.append(p.name)

        ts = time.strftime("%H:%M:%S")
        lines = [f"\n---\n\n## 第 {step} 步 · 尝试 {attempt}（{ts}）\n"]
        labels = ["原图"] + [f"SoM 序号图 {k}" for k in range(1, len(img_rel_paths))]
        for p, label in zip(img_rel_paths, labels):
            lines.append(f"### {label}\n\n![{label}]({p})\n")
        lines.append("### 发给 LLM 的信息\n\n```text\n" + prompt + "\n```\n")
        if thinking:
            lines.append("### 模型思考过程\n\n```text\n" + thinking + "\n```\n")
        lines.append("### LLM 返回的信息\n\n```text\n" + raw_output + "\n```\n")

        parsed_str = "、".join(parsed) if parsed else "（解析失败，见上方返回信息）"
        lines.append(f"**解析动作**：{parsed_str}\n")
        lines.append(f"**执行后状态**：{status}\n")
        if elapsed_s is not None:
            lines.append(f"**本步耗时**：{elapsed_s:.1f} 秒\n")
        if usage:
            seq = int(usage.get("prompt_tokens") or 0) + int(
                usage.get("completion_tokens") or 0)
            lines.append(
                f"**Token 用量**：prompt={usage.get('prompt_tokens', 0)}"
                f"，completion={usage.get('completion_tokens', 0)}"
                f"，序列={seq}\n")
            if usage.get("done_reason"):
                lines.append(f"**生成结束原因**：`{usage['done_reason']}`\n")
            lines.append(
                f"**模型耗时**：prompt_eval="
                f"{float(usage.get('prompt_eval_ms') or 0):.0f} ms"
                f"，eval={float(usage.get('eval_ms') or 0):.0f} ms\n")
        if conclusions:
            numbered = "\n".join(f"- {c}" for c in conclusions)
            lines.append(f"**推理结论（已存入结论记忆）**：\n{numbered}\n")

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return img_rel_paths

    def log_finish(self, reason: str, steps: int, max_steps: int,
                   actions: list, conclusions: list[str],
                   usage: dict | None = None) -> None:
        """运行结束时在 md 末尾追加"测试结束"节。

        reason 由 Runner 组装：任务判定结束（success/fail）、步数耗尽、
        异常中断——复盘时一眼区分"游戏判负"与"框架崩溃"。
        """
        ts = time.strftime("%H:%M:%S")
        seq = " → ".join(a.describe() for a in actions) if actions else "（无）"
        lines = [
            f"\n---\n\n## 测试结束（{ts}）\n",
            f"**结束原因**：{reason}",
            f"**总步数**：{steps}（上限 {max_steps}）",
            f"**动作序列**：{seq}",
            f"**推理结论**：{len(conclusions)} 条存入结论记忆\n",
        ]
        if usage:
            lines.append(
                f"**Token 合计**：prompt={usage.get('prompt_tokens', 0)}"
                f"，completion={usage.get('completion_tokens', 0)}"
                f"，调用={usage.get('calls', 0)} 次\n")
            lines.append(
                f"**上下文峰值**：{usage.get('max_seq', 0)} tokens"
                f"（prompt max={usage.get('max_prompt_tokens', 0)}"
                f"，completion max={usage.get('max_completion_tokens', 0)}）\n")
            lines.append(
                f"**截断次数**：{usage.get('length_stops', 0)} 次 "
                f"done_reason=length\n")
            lines.append(
                f"**模型耗时合计**：prompt_eval="
                f"{float(usage.get('prompt_eval_ms') or 0) / 1000:.2f} s"
                f"，eval={float(usage.get('eval_ms') or 0) / 1000:.2f} s\n")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
