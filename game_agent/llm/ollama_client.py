import base64
import json

import httpx

from game_agent.config.settings import AppSettings
from game_agent.llm.actions import ACTION_TOOLS, merge_tool_calls
from game_agent.llm.base import BaseLLMClient, LLMCapabilities


class OllamaClient(BaseLLMClient):
    def __init__(self, settings: AppSettings, function_calling: bool = False,
                 num_ctx: int | None = None,
                 temperature: float | None = None,
                 top_p: float | None = None,
                 num_predict: int | None = None,
                 think: bool | None = None):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.function_calling = function_calling
        self.num_ctx = settings.OLLAMA_NUM_CTX if num_ctx is None else num_ctx
        self.temperature = settings.OLLAMA_TEMPERATURE if temperature is None else temperature
        self.top_p = settings.OLLAMA_TOP_P if top_p is None else top_p
        self.num_predict = settings.OLLAMA_NUM_PREDICT if num_predict is None else num_predict
        self.think = self._parse_think(settings.OLLAMA_THINK) if think is None else think
        # 最近一次响应的用量与思考过程，供 trace/benchmark 采集
        self.last_usage: dict | None = None
        self.last_thinking = ""

    @property
    def capabilities(self) -> LLMCapabilities:
        # 图片/tools 字段由服务端模型解释；具体模型是否支持需自行确认。
        return LLMCapabilities(vision=True,
                               function_calling=self.function_calling,
                               streaming=True)

    @staticmethod
    def _parse_think(value) -> bool | None:
        """default/auto → 不传字段；true/false → 显式开关 thinking。"""
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in ("", "default", "auto"):
            return None
        return text in ("1", "true", "yes", "on")

    def _request_error(self, e: Exception) -> Exception:
        """把 httpx 的空消息异常翻译成可诊断的错误。"""
        if isinstance(e, httpx.TimeoutException):
            return Exception(
                f"Ollama 请求超时（{self.timeout}s，模型 {self.model}）："
                f"{type(e).__name__}。首次加载大模型可调大 OLLAMA_TIMEOUT")
        if isinstance(e, httpx.ConnectError):
            return Exception(
                f"无法连接 Ollama（{self.base_url}）：{type(e).__name__}。"
                f"请确认 ollama serve 正在运行")
        return Exception(f"Ollama 请求失败：{type(e).__name__}: {e!r}")

    def _options(self) -> dict:
        options: dict = {}
        if self.num_ctx and self.num_ctx > 0:
            options["num_ctx"] = self.num_ctx
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.top_p is not None:
            options["top_p"] = self.top_p
        if self.num_predict and self.num_predict > 0:
            options["num_predict"] = self.num_predict
        return options

    def _payload(self, messages: list[dict], stream: bool = False) -> dict:
        payload = {"model": self.model, "messages": messages, "stream": stream}
        options = self._options()
        if options:
            payload["options"] = options
        if self.think is not None:
            payload["think"] = self.think
        if self.function_calling:
            payload["tools"] = ACTION_TOOLS
        return payload

    def _record_usage(self, data: dict) -> None:
        """采集 Ollama 的 token 用量与耗时（duration 单位为纳秒）。"""
        self.last_usage = {
            "prompt_tokens": int(data.get("prompt_eval_count") or 0),
            "completion_tokens": int(data.get("eval_count") or 0),
            "prompt_eval_ms": round((data.get("prompt_eval_duration") or 0) / 1_000_000, 1),
            "eval_ms": round((data.get("eval_duration") or 0) / 1_000_000, 1),
            "total_ms": round((data.get("total_duration") or 0) / 1_000_000, 1),
            # stop = 自然结束；length = 触达 num_predict 或上下文上限
            "done_reason": data.get("done_reason") or "",
        }

    def _content(self, response: httpx.Response) -> str:
        """取正文；若模型返回 tool_calls，则归一化成动作 JSON 追加在末尾。"""
        data = response.json()
        self._record_usage(data)
        message = data.get("message") or {}
        self.last_thinking = message.get("thinking", "") or ""
        content = message.get("content", "") or ""
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            content = merge_tool_calls(content, tool_calls)
        return content

    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        messages = self._build_messages(prompt, history)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=self._payload(messages),
                )
                response.raise_for_status()
                return self._content(response)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Ollama 模型 '{self.model}' 未找到或 API 路径错误 (404)。请确保已运行 `ollama pull {self.model}`")
                raise Exception(f"Ollama 请求失败: {e.response.text}")
            except Exception as e:
                raise self._request_error(e) from e

    async def generate_with_images(self, prompt: str, images: list[bytes], history: list[dict] | None = None) -> str:
        messages = self._build_messages(prompt, history)
        messages[-1]["images"] = [base64.b64encode(b).decode() for b in images]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json=self._payload(messages),
                )
                response.raise_for_status()
                return self._content(response)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Ollama 模型 '{self.model}' 未找到或 API 路径错误 (404)。请确保已运行 `ollama pull {self.model}`")
                raise Exception(f"Ollama 请求失败: {e.response.text}")
            except Exception as e:
                raise self._request_error(e) from e

    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        messages = self._build_messages(prompt, history)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                tool_calls: list[dict] = []
                thinking_parts: list[str] = []
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=self._payload(messages, stream=True),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        message = chunk.get("message") or {}
                        if message.get("thinking"):
                            thinking_parts.append(message["thinking"])
                        if message.get("content"):
                            yield message["content"]
                        tool_calls.extend(message.get("tool_calls") or [])
                    self.last_thinking = "".join(thinking_parts)
                    if tool_calls:
                        yield merge_tool_calls("", tool_calls)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Ollama 模型 '{self.model}' 未找到或 API 路径错误 (404)。")
                raise Exception(f"Ollama 流式请求失败: {e.response.text}")
            except Exception as e:
                raise self._request_error(e) from e

    @staticmethod
    def _build_messages(prompt: str, history: list[dict] | None = None) -> list[dict]:
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages
