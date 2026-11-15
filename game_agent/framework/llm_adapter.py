"""把现有 BaseLLMClient 适配成 Runner 需要的窄 Decider 接口。

LLM 可插拔的关键：换模型只动配置，框架零改动。
"""
from __future__ import annotations

from typing import Awaitable, Callable

from game_agent.llm.base import BaseLLMClient

Decider = Callable[[str, list[bytes]], Awaitable[str]]


def make_llm_decider(client: BaseLLMClient) -> Decider:
    async def decide(prompt: str, images: list[bytes]) -> str:
        try:
            return await client.generate_with_images(prompt, images)
        finally:
            # 供 AgentRunner 采集本次调用的 token/耗时；不支持 usage 的客户端为 None
            decide.last_usage = getattr(client, "last_usage", None)
            decide.last_thinking = getattr(client, "last_thinking", "")

    decide.last_usage = None
    decide.last_thinking = ""
    return decide
