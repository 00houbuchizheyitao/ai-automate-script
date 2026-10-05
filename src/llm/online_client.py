"""在线多模态模型客户端：OpenAI 兼容端点（GLM 开放平台等）。

设计要点：
- generate_with_image 以 data-url 附图，适配 GLM-5.3 等多模态模型
- thinking 参数默认禁用（Agent 单步决策要快、输出要干净的 JSON）；
  该字段是 Zhipu 扩展，其他兼容端点可经 ONLINE_THINKING=default 关闭传参
- Agent 路径不依赖 history（上下文由 ContextAssembler 组装进 prompt）
"""
from __future__ import annotations

import base64

import httpx

from src.llm.base import BaseLLMClient


class OnlineLLMClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str,
                 base_url: str | None = None, timeout: int = 120,
                 thinking: str = "off", max_tokens: int | None = None):
        if not api_key:
            raise ValueError(
                "缺少在线模型 API Key：请在项目根目录 .env 中设置 "
                "ONLINE_API_KEY（GLM 开放平台 open.bigmodel.cn 获取）")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.timeout = timeout
        self.thinking = thinking
        # "始终思考"型模型（glm-5.3-flash 等）在复杂 Agent prompt 下可能思考
        # 数千 token——不设上限会生成到客户端超时。4096 实测足够思考+作答。
        self.max_tokens = max_tokens

    # ---------- 请求构造 ----------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def _payload(self, messages: list[dict]) -> dict:
        payload: dict = {"model": self.model, "messages": messages, "stream": False}
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
        # 瞬时网络错误（超时/连接重置）自动重试一次——Agent 循环的管道可靠性
        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(f"{self.base_url}/chat/completions",
                                             headers=self._headers(),
                                             json=self._payload(messages))
                    resp.raise_for_status()
                    data = resp.json()
                    choice = data["choices"][0]
                    content = choice["message"].get("content") or ""
                    if not content.strip() and choice.get("finish_reason") == "length":
                        raise Exception(
                            "模型思考耗尽 max_tokens 预算未输出答案"
                            "（可增大 .env 中 ONLINE_MAX_TOKENS）")
                    return content
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise Exception("API Key 无效或过期（401），请检查 .env 中的 ONLINE_API_KEY")
                raise Exception(f"在线模型请求失败: {e.response.text[:300]}")
            except (KeyError, IndexError) as e:
                raise Exception(f"在线模型响应格式异常: {e}")
            except httpx.HTTPError as e:
                last_err = e
                if attempt == 1:
                    import asyncio
                    await asyncio.sleep(2)  # 瞬时故障，短暂等待后重试
        raise Exception(f"连接在线模型失败（已重试）: {last_err}")

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
