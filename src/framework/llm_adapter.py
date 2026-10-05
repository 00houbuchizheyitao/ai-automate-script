"""把现有 BaseLLMClient 适配成 Runner 需要的窄 Decider 接口。

LLM 可插拔的关键：换模型只动配置，框架零改动。
"""
from __future__ import annotations

from typing import Awaitable, Callable

from src.llm.base import BaseLLMClient

Decider = Callable[[str, list[bytes]], Awaitable[str]]


def make_llm_decider(client: BaseLLMClient) -> Decider:
    async def decide(prompt: str, images: list[bytes]) -> str:
        return await client.generate_with_images(prompt, images)
    return decide
