"""OllamaClient 工具调用测试（httpx MockTransport，无网络）。"""
import json

import httpx
import pytest

from game_agent.config.settings import AppSettings
from game_agent.llm.ollama_client import OllamaClient


def _settings() -> AppSettings:
    settings = AppSettings()
    settings.OLLAMA_BASE_URL = "https://fake.example"
    settings.OLLAMA_MODEL = "qwen-test"
    settings.OLLAMA_TIMEOUT = 5
    settings.OLLAMA_NUM_CTX = 8192
    settings.OLLAMA_TEMPERATURE = 0.2
    settings.OLLAMA_TOP_P = 0.9
    settings.OLLAMA_NUM_PREDICT = 4096
    settings.OLLAMA_THINK = "default"
    return settings


def _patch_asyncclient(monkeypatch, capture: dict, response_json: dict):
    import game_agent.llm.ollama_client as mod

    real_client = httpx.AsyncClient

    class CapturingClient(real_client):
        def __init__(self, **kwargs):
            kwargs["transport"] = httpx.MockTransport(
                lambda request: _handler(request, capture, response_json))
            super().__init__(**kwargs)

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kw: CapturingClient(**kw))


def _handler(request: httpx.Request, capture: dict, response_json: dict) -> httpx.Response:
    capture["payload"] = json.loads(request.content)
    return httpx.Response(200, json=response_json, request=request)


@pytest.mark.asyncio
async def test_fc_payload_includes_tools(monkeypatch):
    capture: dict = {}
    _patch_asyncclient(monkeypatch, capture, {"message": {"content": "ok"}})

    client = OllamaClient(_settings(), function_calling=True)
    out = await client.generate("hi")

    assert out == "ok"
    assert "tools" in capture["payload"]
    assert capture["payload"]["tools"][0]["function"]["name"] == "click"


@pytest.mark.asyncio
async def test_no_tools_when_fc_disabled(monkeypatch):
    capture: dict = {}
    _patch_asyncclient(monkeypatch, capture, {"message": {"content": "ok"}})

    client = OllamaClient(_settings())
    await client.generate("hi")

    assert "tools" not in capture["payload"]


@pytest.mark.asyncio
async def test_tool_call_arguments_object_is_merged(monkeypatch):
    capture: dict = {}
    response = {"message": {"content": "", "tool_calls": [
        {"function": {"name": "click", "arguments": {
            "ids": ["30", "70"], "conclusions": ["31/32 必有一雷"]}}},
    ]}}
    _patch_asyncclient(monkeypatch, capture, response)

    client = OllamaClient(_settings(), function_calling=True)
    out = await client.generate_with_images("hi", [b"\x89PNG"])

    assert json.loads(out) == {
        "type": "click",
        "ids": ["30", "70"],
        "conclusions": ["31/32 必有一雷"],
    }
    assert capture["payload"]["messages"][-1]["images"]
    assert "tools" in capture["payload"]


@pytest.mark.asyncio
async def test_tool_call_arguments_string_is_merged(monkeypatch):
    capture: dict = {}
    response = {"message": {"content": "", "tool_calls": [
        {"function": {"name": "flag", "arguments": '{"ids": ["1", "2"]}'}},
    ]}}
    _patch_asyncclient(monkeypatch, capture, response)

    client = OllamaClient(_settings(), function_calling=True)
    out = await client.generate("hi")

    assert json.loads(out) == {"type": "flag", "ids": ["1", "2"]}


def test_capabilities_reflect_fc_flag():
    assert OllamaClient(_settings(), function_calling=True).capabilities.function_calling is True
    assert OllamaClient(_settings()).capabilities.function_calling is False


@pytest.mark.asyncio
async def test_options_payload(monkeypatch):
    capture: dict = {}
    _patch_asyncclient(monkeypatch, capture, {"message": {"content": "ok"}})

    client = OllamaClient(_settings())
    await client.generate("hi")

    assert capture["payload"]["options"] == {
        "num_ctx": 8192,
        "temperature": 0.2,
        "top_p": 0.9,
        "num_predict": 4096,
    }


def test_options_omit_zero_values():
    client = OllamaClient(_settings(), num_ctx=0, num_predict=0)
    assert client._options() == {"temperature": 0.2, "top_p": 0.9}


@pytest.mark.asyncio
async def test_think_payload_and_thinking_capture(monkeypatch):
    capture: dict = {}
    response = {"message": {"content": "ok", "thinking": "先看棋盘，再判断"}}
    _patch_asyncclient(monkeypatch, capture, response)

    client = OllamaClient(_settings(), think=True)
    out = await client.generate("hi")

    assert out == "ok"
    assert capture["payload"]["think"] is True
    assert client.last_thinking == "先看棋盘，再判断"


def test_think_parsing():
    settings = _settings()
    settings.OLLAMA_THINK = "true"
    assert OllamaClient(settings).think is True
    settings.OLLAMA_THINK = "false"
    assert OllamaClient(settings).think is False
    settings.OLLAMA_THINK = "default"
    assert OllamaClient(settings).think is None


def test_request_error_messages_are_diagnosable():
    client = OllamaClient(_settings())
    timeout = client._request_error(httpx.ReadTimeout(""))
    assert "超时" in str(timeout)
    assert "ReadTimeout" in str(timeout)

    connect = client._request_error(httpx.ConnectError(""))
    assert "无法连接" in str(connect)
    assert "ConnectError" in str(connect)


@pytest.mark.asyncio
async def test_usage_is_recorded(monkeypatch):
    capture: dict = {}
    response = {
        "message": {"content": "ok"},
        "prompt_eval_count": 1234,
        "eval_count": 56,
        "prompt_eval_duration": 1_500_000_000,
        "eval_duration": 2_000_000_000,
        "total_duration": 3_600_000_000,
        "done_reason": "length",
    }
    _patch_asyncclient(monkeypatch, capture, response)

    client = OllamaClient(_settings())
    await client.generate("hi")

    assert client.last_usage == {
        "prompt_tokens": 1234,
        "completion_tokens": 56,
        "prompt_eval_ms": 1500.0,
        "eval_ms": 2000.0,
        "total_ms": 3600.0,
        "done_reason": "length",
    }
