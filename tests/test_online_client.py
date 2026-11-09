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


def _sse(body: dict) -> str:
    """把非流式响应体转成 OpenAI 兼容 SSE 文本（content 拆两个 delta）"""
    content = body["choices"][0]["message"]["content"]
    half = max(1, len(content) // 2)
    parts = [
        json.dumps({"choices": [{"delta": {"content": content[:half]}}]}),
        json.dumps({"choices": [{"delta": {"content": content[half:]}}]}),
        json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
    ]
    return "".join(f"data: {p}\n\n" for p in parts) + "data: [DONE]\n\n"


def _handler(request: httpx.Request, capture: dict, response_body: dict) -> httpx.Response:
    capture["url"] = str(request.url)
    capture["headers"] = dict(request.headers)
    capture["payload"] = json.loads(request.content)
    return httpx.Response(200, text=_sse(response_body),
                          headers={"content-type": "text/event-stream"})


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
    assert payload["stream"] is True  # 流式：字节流不断 = 服务端活着（心跳式挂死检测）
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


def _sse_tool_call(name: str, arguments: str) -> str:
    """模拟 FC 流式：工具名先到，arguments 分两个碎片到达（拼接验证）"""
    cut = len(arguments) // 2 + 1
    parts = [
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_1", "type": "function",
            "function": {"name": name, "arguments": ""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": arguments[:cut]}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": arguments[cut:]}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    return "".join(f"data: {json.dumps(p)}\n\n" for p in parts) + "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_function_calling_payload_and_tool_call_merge(monkeypatch):
    """FC 模式：请求带 tools 声明；流式 tool_calls 碎片拼接后产出动作 JSON，
    且能被 Runner 的 parse_action 直接解析（两种协议共用同一解析入口）。"""
    import src.llm.online_client as mod
    from src.framework.types import parse_action

    capture: dict = {}
    real_client = httpx.AsyncClient
    args = '{"ids": ["30", "70"], "conclusions": ["31与32恰有1雷"]}'

    def handler(request: httpx.Request) -> httpx.Response:
        capture["payload"] = json.loads(request.content)
        return httpx.Response(200, text=_sse_tool_call("click", args),
                              headers={"content-type": "text/event-stream"})

    class CapturingClient(real_client):
        def __init__(self, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(**kwargs)

    monkeypatch.setattr(mod.httpx, "AsyncClient",
                        lambda **kw: CapturingClient(**kw))

    client = OnlineLLMClient(api_key="k", model="glm-5.3-flash",
                             base_url="https://fake.example/v4", timeout=5,
                             function_calling=True)
    out = await client.generate_with_images("决策", [b"\x89PNG"])

    # 请求侧：tools 声明存在，工具名与动作类型一致
    tools = capture["payload"]["tools"]
    assert [t["function"]["name"] for t in tools] == ["click", "flag"]
    assert "ids" in tools[0]["function"]["parameters"]["properties"]

    # 响应侧：tool_calls 碎片拼接 → 动作 JSON → 现有解析器可直接消费
    action = parse_action(out)
    assert action.type == "click"
    assert action.ids == ("30", "70")
    assert action.conclusions == ("31与32恰有1雷",)


@pytest.mark.asyncio
async def test_progress_callback_reports_received_chars(monkeypatch):
    """流式进度回调：每收到增量报告已接收字符数（长思考期的存活证明）"""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": "一段不超过三十秒的答案"}}]}
        return httpx.Response(200, text=_sse(body),
                              headers={"content-type": "text/event-stream"})

    # 直接替换 transport 注入：进度与 payload 无关，只需流式内容
    real_client = httpx.AsyncClient

    class CapturingClient(real_client):
        def __init__(self, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(**kwargs)

    import src.llm.online_client as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient",
                        lambda **kw: CapturingClient(**kw))

    client = OnlineLLMClient(api_key="k", model="m",
                             base_url="https://fake.example/v4", timeout=5,
                             progress_callback=calls.append,
                             progress_interval_s=0)  # 0 = 每个增量都回调（测试用）
    out = await client.generate("hi")
    assert out == "一段不超过三十秒的答案"
    assert calls and calls[-1] == len(out)   # 最后报告值 = 已接收总字符数
    assert calls == sorted(calls)            # 单调递增


@pytest.mark.asyncio
async def test_non_fc_payload_has_no_tools(monkeypatch):
    """默认（prompt-json）模式不得携带 tools——对照组纯净"""
    capture: dict = {}
    body = {"choices": [{"message": {"content": "ok"}}]}
    _patch_asyncclient(monkeypatch, capture, body)

    client = OnlineLLMClient(api_key="k", model="m",
                             base_url="https://fake.example/v4")
    await client.generate("hi")
    assert "tools" not in capture["payload"]


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


@pytest.mark.asyncio
async def test_hang_timeout_retried_then_recovers(monkeypatch):
    """流式挂死检测：第一次请求字节流中断（ReadTimeout）→ 自动重试 → 恢复。

    对应真实事故：智谱服务端间歇性挂起（连接吊死不吐字节），非流式时代
    客户端无限等待；流式下读超时=字节间隔上限，挂死几十秒即可判定。
    """
    import src.llm.online_client as mod

    real_client = httpx.AsyncClient
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("字节流中断", request=request)
        body = {"choices": [{"message": {"content": "恢复后的答案"}}]}
        return httpx.Response(200, text=_sse(body),
                              headers={"content-type": "text/event-stream"})

    class CapturingClient(real_client):
        def __init__(self, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(**kwargs)

    monkeypatch.setattr(mod.httpx, "AsyncClient",
                        lambda **kw: CapturingClient(**kw))

    client = OnlineLLMClient(api_key="k", model="m",
                             base_url="https://fake.example/v4", timeout=5)
    out = await client.generate("你好")
    assert out == "恢复后的答案"
    assert calls["n"] == 2  # 挂死后重试成功
