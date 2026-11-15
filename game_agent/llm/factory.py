"""LLM 客户端工厂：把 provider 选择从入口脚本收回到框架配置。

支持：
- online：任意 OpenAI 兼容 /chat/completions 端点（GLM、DeepSeek、Qwen 等）
- ollama：本地 Ollama

使用者只需配置 LLM_PROVIDER / 模型名，不再关心具体客户端类。
"""
from __future__ import annotations

from typing import Callable

from game_agent.config.settings import AppSettings
from game_agent.llm.base import BaseLLMClient, ensure_capabilities
from game_agent.llm.ollama_client import OllamaClient
from game_agent.llm.online_client import OnlineLLMClient

SUPPORTED_PROVIDERS = ("ollama", "online")
_PROVIDER_ALIASES = {
    "ollama": "ollama",
    "online": "online",
    "openai": "online",
    "openai-compatible": "online",
}


class LLMFactoryError(ValueError):
    """provider 配置错误，或该后端不支持请求的选项。"""


def create_llm_client(
    settings: AppSettings,
    provider: str | None = None,
    model: str | None = None,
    *,
    function_calling: bool = False,
    progress_callback: Callable[[int], None] | None = None,
) -> BaseLLMClient:
    """按 provider 创建客户端；未知 provider / 不支持的选项立即报错。

    模型要求：必须支持图像输入（Runner 每步发送原图 + SoM 标注图）；
    function_calling=True 时还要求端点支持 tools。
    本函数只校验客户端传输层能力，具体模型能力由调用方保证。
    """
    requested = (provider or settings.LLM_PROVIDER).strip().lower()
    name = _PROVIDER_ALIASES.get(requested)
    if name is None:
        raise LLMFactoryError(
            f"未知 LLM_PROVIDER={requested!r}；支持: {', '.join(SUPPORTED_PROVIDERS)}")

    if name == "online":
        client: BaseLLMClient = OnlineLLMClient(
            api_key=settings.ONLINE_API_KEY,
            model=model or settings.ONLINE_MODEL,
            base_url=settings.ONLINE_BASE_URL,
            timeout=settings.ONLINE_TIMEOUT,
            thinking=settings.ONLINE_THINKING,
            max_tokens=settings.ONLINE_MAX_TOKENS,
            function_calling=function_calling,
            progress_callback=progress_callback,
        )
    else:
        if progress_callback is not None:
            raise LLMFactoryError("Ollama 后端暂不支持 progress_callback")
        client = OllamaClient(settings, function_calling=function_calling)
        if model:
            client.model = model

    # 现有 Runner 每步都发送截图；没有视觉能力的客户端无法完成闭环。
    ensure_capabilities(client, vision=True, function_calling=function_calling)
    return client
