"""OnlineLLMClient 测试：payload 构造与响应解析（httpx MockTransport，无网络）。"""
import base64
import json

import httpx
import pytest

from src.llm.online_client import OnlineLLMClient


def _client_with_transport(handler) -> OnlineLLMClient:
    client = OnlineLLMClient(api_key="test-key", model="glm-5.3-flash",
                             base_url="https://fake.example/v4", timeout=5,
                             thinking="off")
    # 注入 MockTransport：绕过真实网络，同时捕获请求
    client._transport = httpx.MockTransport(handler)
    return client


def _patch_asyncclient(monkeypatch, capture: dict, response_body: dict):
    """替换 OnlineLLMClient 内部使用的 httpx.AsyncClient 以捕获请求"""
    real_client = httpx.AsyncClient

    class CapturingClient(real_client):
        def __init__(self, **kwargs):
            kwargs["transport"] = httpx.MockTransport(
                lambda request: _handler(request, capture, response_body))
            super().__init__(**kwargs)

    def factory(**kwargs):
        return CapturingClient(**kwargs)

    import src.llm.online_client as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient", factory)


def _handler(request: httpx.Request, capture: dict, response_body: dict) -> httpx.Response:
    capture["url"] = str(request.url)
    capture["headers"] = dict(request.headers)
    capture["payload"] = json.loads(request.content)
    return httpx.Response(200, json=response_body)


@pytest.mark.asyncio
async def test_generate_with_image_payload(monkeypatch):
    capture: dict = {}
    body = {"choices": [{"message": {"content": '{"type": "click", "x": 1, "y": 2}'}}]}
    _patch_asyncclient(monkeypatch, capture, body)

    client = OnlineLLMClient(api_key="k", model="glm-5.3-flash",
                             base_url="https://fake.example/v4", thinking="off")
    png = base64.b64encode(b"\x89PNG-fake").decode()
    out = await client.generate_with_image("决策", b"\x89PNG-fake")

    assert out.startswith('{"type"')
    assert capture["url"] == "https://fake.example/v4/chat/completions"
    assert capture["headers"]["authorization"] == "Bearer k"
    payload = capture["payload"]
    assert payload["model"] == "glm-5.3-flash"
    assert payload["thinking"] == {"type": "disabled"}
    content = payload["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "决策"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_thinking_on_and_text_only(monkeypatch):
    capture: dict = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    _patch_asyncclient(monkeypatch, capture, body)

    client = OnlineLLMClient(api_key="k", model="m",
                             base_url="https://fake.example/v4", thinking="on")
    await client.generate("你好")

    assert capture["payload"]["thinking"] == {"type": "enabled"}
    assert capture["payload"]["messages"][-1]["content"] == "你好"


def test_missing_api_key_raises():
    with pytest.raises(ValueError, match="ONLINE_API_KEY"):
        OnlineLLMClient(api_key="", model="m")


@pytest.mark.asyncio
async def test_image_normalized_to_rgb_png(monkeypatch):
    """mss 风格 RGBA 截图应被重编码为标准 RGB PNG 再发送（规避服务端挂起）"""
    import io

    from PIL import Image

    capture: dict = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    _patch_asyncclient(monkeypatch, capture, body)

    # 构造 RGBA 图像（mss 截图风格）
    img = Image.new("RGBA", (40, 40), (100, 100, 100, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    rgba_png = buf.getvalue()

    client = OnlineLLMClient(api_key="k", model="m",
                             base_url="https://fake.example/v4")
    await client.generate_with_image("决策", rgba_png)

    sent_url = capture["payload"]["messages"][-1]["content"][1]["image_url"]["url"]
    assert sent_url.startswith("data:image/png;base64,")
    sent_bytes = base64.b64decode(sent_url.split(",", 1)[1])
    sent_img = Image.open(io.BytesIO(sent_bytes))
    assert sent_img.mode == "RGB"  # 已重编码为 RGB
