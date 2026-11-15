"""LLM 工厂与能力声明的单元测试（不发起网络请求）。"""
import pytest

from game_agent.config.settings import AppSettings
from game_agent.llm import (
    CapabilityError,
    LLMFactoryError,
    OllamaClient,
    OnlineLLMClient,
    create_llm_client,
    ensure_capabilities,
)


def _settings() -> AppSettings:
    settings = AppSettings()
    settings.LLM_PROVIDER = "ollama"
    settings.ONLINE_API_KEY = "test-key"
    return settings


def test_factory_builds_ollama_client():
    client = create_llm_client(_settings(), provider="ollama", model="demo")
    assert isinstance(client, OllamaClient)
    assert client.model == "demo"
    assert client.capabilities.vision is True
    assert client.capabilities.function_calling is False


def test_factory_builds_online_client_and_honors_fc():
    client = create_llm_client(
        _settings(), provider="online", model="demo", function_calling=True)
    assert isinstance(client, OnlineLLMClient)
    assert client.model == "demo"
    assert client.capabilities.vision is True
    assert client.capabilities.function_calling is True


def test_factory_accepts_openai_alias():
    client = create_llm_client(_settings(), provider="openai-compatible")
    assert isinstance(client, OnlineLLMClient)


def test_factory_rejects_unknown_provider():
    with pytest.raises(LLMFactoryError, match="未知 LLM_PROVIDER"):
        create_llm_client(_settings(), provider="unknown")


def test_factory_allows_fc_on_ollama():
    client = create_llm_client(_settings(), provider="ollama", function_calling=True)
    assert isinstance(client, OllamaClient)
    assert client.capabilities.function_calling is True


def test_ensure_capabilities_reports_missing():
    client = create_llm_client(_settings(), provider="ollama")
    with pytest.raises(CapabilityError, match="function_calling"):
        ensure_capabilities(client, function_calling=True)
