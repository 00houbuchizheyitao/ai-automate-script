"""在线多模态模型客户端：OpenAI 兼容端点（GLM 开放平台等）。

设计要点：
- generate_with_image 以 data-url 附图，适配 GLM-5.3 等多模态模型
- thinking 参数默认禁用（Agent 单步决策要快、输出要干净的 JSON）；
  该字段是 Zhipu 扩展，其他兼容端点可经 ONLINE_THINKING=default 关闭传参
- Agent 路径不依赖 history（上下文由 ContextAssembler 组装进 prompt）
"""
from __future__ import annotations

import base64
import json
import time
from typing import Callable

import httpx

from game_agent.llm.actions import ACTION_TOOLS, merge_tool_calls
from game_agent.llm.base import BaseLLMClient, LLMCapabilities


class OnlineLLMClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str,
                 base_url: str | None = None, timeout: int = 120,
                 thinking: str = "off", max_tokens: int | None = None,
                 function_calling: bool = False,
                 progress_callback: Callable[[int], None] | None = None,
                 progress_interval_s: float = 30.0):
        if not api_key:
            raise ValueError(
                "缺少在线模型 API Key：请在项目根目录 .env 中设置 "
                "ONLINE_API_KEY（GLM 开放平台 open.bigmodel.cn 获取）")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.timeout = timeout
        self.thinking = thinking
        # max_tokens=0/None → 请求不带该字段，服务端用模型输出上限兜底
        # （始终思考型模型推荐：思考量随局面复杂度波动，框架侧设顶会把
        # 思考截断成空答案——token 照计费却没有产出）；正值 = 生成硬顶
        self.max_tokens = max_tokens
        # Function Calling 开关：动作改由 API 层工具声明（硬约束），
        # 返回值仍序列化成动作 JSON 文本，对上层解析器零侵入
        self.function_calling = function_calling
        # 流式进度回调：每隔 interval 秒以"已接收字符数"回调一次，
        # 用于在控制台证明"仍在思考"（长思考 30+ 分钟时不是卡死）。
        # interval<=0 = 每收到一个增量就回调（测试用）
        self.progress_callback = progress_callback
        self.progress_interval_s = progress_interval_s

    @property
    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            vision=True,
            # 反映当前实例是否真的会发送 tools；--fc 由构造参数开启
            function_calling=self.function_calling,
            streaming=False,  # 公开的 stream_generate 是一次性产出
        )

    # ---------- 请求构造 ----------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def _payload(self, messages: list[dict]) -> dict:
        payload: dict = {"model": self.model, "messages": messages, "stream": True}
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        # thinking 配置语义（兼容不同模型）：
        #   off → 关闭思考（部分模型支持）；on → 默认强度开启；
        #   low/high/max → 始终思考型模型（如 glm-5.3-flash）的思考速度档位
        if self.thinking == "off":
            payload["thinking"] = {"type": "disabled"}
        elif self.thinking == "on":
            payload["thinking"] = {"type": "enabled"}
        elif self.thinking in ("low", "high", "max"):
            payload["thinking"] = {"type": "enabled", "speed": self.thinking}
        if self.function_calling:
            payload["tools"] = ACTION_TOOLS
        return payload

    @staticmethod
    def _user_content(prompt: str, images: list[bytes]):
        if not images:
            return prompt  # 纯文本请求用字符串 content，兼容性最好
        parts: list[dict] = [{"type": "text", "text": prompt}]
        for b in images:
            b64 = base64.b64encode(OnlineLLMClient._normalize_image(b)).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}})
        return parts

    def _messages(self, prompt: str, history: list[dict] | None,
                  images: list[bytes] | None = None) -> list[dict]:
        messages = list(history or [])
        messages.append({"role": "user",
                         "content": self._user_content(prompt, images or [])})
        return messages

    # ---------- 请求执行 ----------

    async def _chat(self, messages: list[dict]) -> str:
        # 流式请求 + 心跳式挂死检测：服务端立即持续推送增量（思考阶段推
        # reasoning_content，作答阶段推 content），字节流不断 = 活着。
        # 读超时语义 = "两次字节之间的最大间隔"（ONLINE_TIMEOUT，几十秒）：
        # 服务端间歇性挂起时字节流中断 → 快速超时 → 自动重试一次，无需
        # 等待整个生成周期。max_tokens 与该超时从此解耦（流式下两者都安全）。
        timeout = httpx.Timeout(self.timeout if self.timeout > 0 else None,
                                connect=10.0)
        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                chunks: list[str] = []
                finish: str | None = None
                tool_calls: dict[int, dict] = {}  # index → {name, arguments}（流式碎片累积）
                received = 0                     # 已接收字符数（含思考增量）
                last_progress = time.monotonic()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                            "POST", f"{self.base_url}/chat/completions",
                            headers=self._headers(),
                            json=self._payload(messages)) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue  # SSE 空行/注释行
                            data = line[len("data:"):].strip()
                            if data == "[DONE]":
                                break
                            try:
                                obj = json.loads(data)
                            except json.JSONDecodeError:
                                continue  # 容忍无法解析的心跳行
                            choice = (obj.get("choices") or [{}])[0]
                            delta = choice.get("delta") or {}
                            if delta.get("content"):
                                chunks.append(delta["content"])
                                received += len(delta["content"])
                            # 思考期增量（智谱 reasoning_content）只用于进度显示，
                            # 不进最终答案——它证明服务端仍在生成
                            if delta.get("reasoning_content"):
                                received += len(delta["reasoning_content"])
                            if self.progress_callback and self.progress_interval_s >= 0:
                                now = time.monotonic()
                                if now - last_progress >= self.progress_interval_s:
                                    last_progress = now
                                    try:
                                        self.progress_callback(received)
                                    except Exception:
                                        pass  # 进度回调异常不影响请求
                            for tc in delta.get("tool_calls") or []:
                                slot = tool_calls.setdefault(
                                    tc.get("index", 0),
                                    {"name": "", "arguments": ""})
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] += fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments"] += fn["arguments"]
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
                content = "".join(chunks)
                if tool_calls:
                    content = merge_tool_calls(
                        content,
                        [{"function": {"name": slot.get("name", ""),
                                       "arguments": slot.get("arguments", "")}}
                         for _, slot in sorted(tool_calls.items())],
                    )
                if not content.strip() and finish == "length":
                    raise Exception(
                        "响应被生成长度上限截断且答案为空（finish_reason=length）。"
                        "若 .env 中 ONLINE_MAX_TOKENS>0 可调大或改为 0（不限制）；"
                        "若已为 0 则触达服务端模型输出上限")
                return content
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 401:
                    raise Exception("API Key 无效或过期（401），请检查 .env 中的 ONLINE_API_KEY")
                detail = e.response.text[:300]
                if status in (400, 422):
                    hint = self._capability_hint(detail)
                    if hint:
                        raise Exception(
                            f"在线模型请求失败（{status}，可能是模型能力不匹配）："
                            f"{detail}\n{hint}")
                raise Exception(f"在线模型请求失败: {detail}")
            except (KeyError, IndexError) as e:
                raise Exception(f"在线模型响应格式异常: {e}")
            except httpx.HTTPError as e:
                last_err = e
                if attempt == 1:
                    import asyncio
                    await asyncio.sleep(2)  # 瞬时故障/挂死超时，短暂等待后重试
        raise Exception(f"连接在线模型失败（已重试）: {last_err}")

    @staticmethod
    def _capability_hint(detail: str) -> str:
        """把 400/422 的原始响应翻译成能力不匹配提示（无匹配时返回空串）。"""
        text = detail.lower()
        hints: list[str] = []
        if any(k in text for k in ("image", "image_url", "vision", "multimodal", "modality")):
            hints.append(
                "该模型/端点可能不支持图像输入；本框架每步都会发送截图，"
                "请更换支持视觉的模型。")
        if any(k in text for k in ("tool", "function_call", "function calling", "tools")):
            hints.append(
                "该端点可能不支持 function calling；可去掉 --fc，"
                "改用默认 prompt-json 动作协议。")
        return "\n".join(hints)

    # ---------- BaseLLMClient 接口 ----------

    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        return await self._chat(self._messages(prompt, history))

    @staticmethod
    def _normalize_image(image_bytes: bytes) -> bytes:
        """重编码截图为标准 RGB PNG。

        某些截屏库（mss）产出的 PNG 编码会让部分在线视觉服务挂起
        （请求无响应直至超时，重试无效）；同一图像经 PIL 重编码后立即
        正常。重编码失败时退回原始字节。
        """
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return image_bytes

    async def generate_with_images(self, prompt: str, images: list[bytes],
                                   history: list[dict] | None = None) -> str:
        return await self._chat(self._messages(prompt, history, images))

    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        """Agent 路径不使用流式；为接口完整性提供一次性产出。"""
        text = await self.generate(prompt, history)
        yield text
