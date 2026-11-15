"""人类审查工具：把框架将发给 LLM 的完整信息落盘为 markdown。

两个入口：
- HumanDecider：人扮演 LLM 的交互式决策器（每步写 md、终端输入动作）
- dump_llm_view：单发快照——只生成"第一步将会发送的信息"就结束，
  供上真实模型前人工审查信息质量
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from game_agent.framework.context import ContextAssembler
from game_agent.framework.history import HistoryManager
from game_agent.framework.types import Task


def dump_llm_view(env, task: Task, out_dir: str | Path = "llm_views",
                  normalizer: Callable[[bytes], bytes] | None = None) -> Path:
    """把当前帧将发给 LLM 的完整信息写入 markdown，返回 md 路径。

    信息内容与 AgentRunner 第一步的 LLM 调用完全一致（空历史、无反馈）：
    附图（原图 + SoM 标注图等）+ 经 ContextAssembler 组装的完整 prompt。
    normalizer: 与在线客户端相同的图像重编码函数，保证人看到的 = LLM 看到的。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    frame = env.capture()
    prompt = ContextAssembler().build(task, frame, HistoryManager().view(),
                                      screen_size=env.screen_size)
    images = [frame.screenshot] + ([frame.annotated] if frame.annotated else [])

    paths: list[Path] = []
    for k, raw in enumerate(images, 1):
        img_bytes = normalizer(raw) if normalizer else raw
        p = out / f"llm_view_img{k}.png"
        p.write_bytes(img_bytes)
        paths.append(p)

    md = out / "llm_view.md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("# LLM 视角审查（第一步，一字不差）\n\n"
                "API 请求结构：`messages: [{role: user, content: [text部分, 各图片部分]}]`\n\n")
        for k, p in enumerate(paths, 1):
            label = "第一张：原始画面" if k == 1 else f"第 {k} 张：附加图（SoM 编号标注图）"
            f.write(f"![{label}]({p.name}) —— {label}\n\n")
        f.write("## 发送给 LLM 的完整文本\n\n```\n" + prompt + "\n```\n")
    return md


class HumanDecider:
    def __init__(self, log_path: str | Path = "llm_view.md",
                 normalizer: Callable[[bytes], bytes] | None = None,
                 ask: Callable[[str], str] = input):
        """normalizer: 与在线客户端相同的图像重编码函数（保证人看到的 =
        LLM 看到的）；不传则原样保存。ask: 可注入的输入函数（测试用）。"""
        self.log_path = Path(log_path)
        self.normalizer = normalizer
        self.ask = ask
        self.calls = 0
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(
            "# LLM 视角审查日志\n\n"
            "每条记录 = 一次真实的 LLM 调用：截图（image 内容部分）+ "
            "完整文本（text 内容部分，一字不差）。\n"
            "API 请求结构：`messages: [{role: user, content: [text部分, image部分]}]`\n",
            encoding="utf-8")

    async def __call__(self, prompt: str, images: list[bytes]) -> str:
        """满足 Runner 的 Decider 协议：实例可直接调用。"""
        return await self.decide(prompt, images)

    async def decide(self, prompt: str, images: list[bytes]) -> str:
        self.calls += 1
        paths: list[Path] = []
        for k, raw in enumerate(images, 1):
            img_bytes = self.normalizer(raw) if self.normalizer else raw
            img_path = self.log_path.parent / f"{self.log_path.stem}_call{self.calls}_img{k}.png"
            img_path.write_bytes(img_bytes)
            paths.append(img_path)

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n## 决策调用 {self.calls}\n\n")
            for k, p in enumerate(paths, 1):
                label = "原始画面" if k == 1 else f"附加图 {k - 1}（如 SoM 标注图）"
                f.write(f"![{label}]({p.name}) —— {label}\n\n")
            f.write("### 发送给 LLM 的完整文本\n\n"
                    f"```\n{prompt}\n```\n")

        raw = self.ask(
            f"[决策调用{self.calls}] 输入 JSON 动作"
            f"（如 {{\"type\": \"click\", \"id\": \"23\"}} 或 "
            f"{{\"type\": \"click\", \"x\": 100, \"y\": 100}}）> ")
        return raw
